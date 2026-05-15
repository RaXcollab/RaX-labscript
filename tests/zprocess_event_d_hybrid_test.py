"""Empirical validation of D-hybrid PUB-SUB design assumptions.

Validates:
  A1: Parent-side check_broker() actually starts a broker before subprocess spawn.
  A2: parentinfo carries broker_in_port to subprocess (auto-inherited).
  A3: Worker-side Event(role='wait') connects to parent's broker (cross-process).
  A4: event.sub.recv_multipart() bypassing wait() returns ALL messages
      with their distinct identifiers, none discarded.
  A5: Holding event.sublock during a long poll() does not break anything.
  A9: PUSH socket post() is non-blocking under our message rate (~600 msgs in 2s).

Run from labscript-suite root in conda labscript env:
    python tests/zprocess_event_d_hybrid_test.py
Expected runtime: ~5 seconds.
"""
import os
import sys
import time
import threading
import pickle

import zmq
from zprocess import Process, Event
from zprocess.process_tree import _default_process_tree

EVENT_NAME = 'd_hybrid_test_monitor'
NPOSTS = 200          # 100 Hz x 2 sec
POST_INTERVAL = 0.005 # 5 ms between triple-posts -> 600 msgs/sec total


class WorkerProc(Process):
    def run(self):
        # Re-import inside subprocess: _default_process_tree here is the
        # CHILD's tree, which Process._run set up from parentinfo.
        from zprocess.process_tree import _default_process_tree as pt

        # ---- A2: broker_in_port should be non-None (inherited from parent) ----
        bip = pt.broker_in_port
        bop = pt.broker_out_port
        bhost = pt.broker_host
        print(f'[worker] pid={os.getpid()} broker_host={bhost} '
              f'broker_in_port={bip} broker_out_port={bop}', flush=True)
        assert bip is not None, 'A2 FAILED: parentinfo did not carry broker_in_port'

        # ---- A3 (init): Event(role='wait') connects to parent's broker ----
        try:
            event = Event(EVENT_NAME, role='wait')
        except Exception as e:
            print(f'[worker] A3 FAILED at Event init: {type(e).__name__}: {e}',
                  flush=True)
            self.to_parent.put(('FAIL', f'Event init: {e}'))
            return
        print('[worker] Event(role=wait) init succeeded (welcome message received)',
              flush=True)

        cache = {}
        msg_count = [0]
        drain_errors = []
        stop = threading.Event()

        def drain():
            while not stop.is_set():
                try:
                    # ---- A5: hold sublock during a long poll ----
                    with event.sublock:
                        if not event.sub.poll(200, zmq.POLLIN):
                            continue
                        # ---- A4: bypass wait()'s identifier filter ----
                        encoded_name, eid, data = event.sub.recv_multipart()
                    cache[eid.decode('utf8')] = pickle.loads(data)
                    msg_count[0] += 1
                except Exception as e:
                    drain_errors.append(f'{type(e).__name__}: {e}')
                    if len(drain_errors) > 5:
                        break
                    time.sleep(0.1)

        t = threading.Thread(target=drain, daemon=True)
        t.start()

        # Tell parent we are ready to receive posts.
        self.to_parent.put(('READY', None))

        # Wait for parent's STOP signal via inherited zprocess queue.
        signal = self.from_parent.get()
        stop.set()
        t.join(timeout=2.0)

        # ---- Report results ----
        result = {
            'messages_received': msg_count[0],
            'cache_keys': sorted(cache.keys()),
            'cache_values': cache,
            'drain_errors': drain_errors,
            'broker_in_port': bip,
        }
        self.to_parent.put(('RESULT', result))


def parent_main():
    # ---- A1: module-level check_broker spins up an EventBroker in parent ----
    _default_process_tree.check_broker()
    parent_bip = _default_process_tree.broker_in_port
    parent_bop = _default_process_tree.broker_out_port
    print(f'[parent] check_broker done; broker_in_port={parent_bip} '
          f'broker_out_port={parent_bop}', flush=True)
    assert parent_bip is not None, 'A1 FAILED: parent has no broker after check_broker'

    print('[parent] starting worker subprocess...', flush=True)
    worker = WorkerProc()
    to_child, from_child = worker.start()

    # Wait for worker to confirm it is subscribed and draining.
    tag, payload = from_child.get()
    if tag == 'FAIL':
        print(f'[parent] worker reported FAIL during init: {payload}', flush=True)
        worker.terminate(wait_timeout=5)
        sys.exit(1)
    assert tag == 'READY', f'unexpected worker init tag: {tag}'
    print('[parent] worker is READY; creating Event(role=post)', flush=True)

    poster = Event(EVENT_NAME, role='post')

    # ---- A9: measure post() latency ----
    post_latencies = []
    t_start = time.perf_counter()
    for i in range(NPOSTS):
        t0 = time.perf_counter()
        poster.post('chan_A', i * 1.0)
        poster.post('chan_B', i * 2.0)
        poster.post('chan_C', i * 3.0)
        post_latencies.append((time.perf_counter() - t0) * 1e6)
        time.sleep(POST_INTERVAL)
    t_elapsed = time.perf_counter() - t_start

    # Allow drain thread to flush pending messages.
    time.sleep(0.5)

    # Send STOP and collect results.
    to_child.put('STOP')
    tag, result = from_child.get()
    worker.terminate(wait_timeout=5)
    assert tag == 'RESULT', f'unexpected worker result tag: {tag}'

    # ---- Analysis ----
    sorted_lat = sorted(post_latencies)
    median_us = sorted_lat[NPOSTS // 2]
    p99_us = sorted_lat[int(NPOSTS * 0.99)]
    max_us = max(post_latencies)
    expected_total = NPOSTS * 3

    print('')
    print('=' * 60)
    print('RESULTS')
    print('=' * 60)
    print(f'A1 broker started in parent      : PASS '
          f'(broker_in_port={parent_bip})')
    print(f'A2 broker_in_port inherited      : '
          f'{"PASS" if result["broker_in_port"] == parent_bip else "FAIL"} '
          f'(worker saw {result["broker_in_port"]}, parent has {parent_bip})')
    print(f'A3 worker subscribed cross-proc  : PASS (welcome msg received)')
    print(f'A4 distinct identifiers received : '
          f'{"PASS" if set(result["cache_keys"]) == {"chan_A","chan_B","chan_C"} else "FAIL"} '
          f'(keys={result["cache_keys"]})')
    print(f'A4 last-write-wins values        : {result["cache_values"]}')
    print(f'   Expected: chan_A=199.0 chan_B=398.0 chan_C=597.0')
    print(f'A5 drain loop ran without errors : '
          f'{"PASS" if not result["drain_errors"] else "FAIL"} '
          f'({len(result["drain_errors"])} errors)')
    if result['drain_errors']:
        for e in result['drain_errors']:
            print(f'     {e}')
    print(f'A4 message count                 : received={result["messages_received"]}/'
          f'{expected_total} '
          f'({"PASS" if result["messages_received"] == expected_total else "PARTIAL"})')
    print(f'A9 post() latency                : '
          f'median={median_us:.1f}us p99={p99_us:.1f}us max={max_us:.1f}us '
          f'({"PASS" if median_us < 1000 else "FAIL"} threshold 1000us)')
    print(f'   Total post-loop wall time     : {t_elapsed*1000:.1f}ms '
          f'(expected ~{NPOSTS*POST_INTERVAL*1000:.0f}ms)')
    print('=' * 60)


if __name__ == '__main__':
    parent_main()
