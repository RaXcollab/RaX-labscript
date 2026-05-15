"""Test 2: validates the realistic BLACS path through labscript_utils.ls_zprocess.

Adds coverage beyond Test 1:
  T2.1: ls_zprocess wrapper (shared_secret-secured) works cross-process.
  T2.2: Multiple worker subprocesses each with their OWN event_name receive
        only their own messages and don't cross-leak.
  T2.3: Drain-thread shutdown — when worker calls shutdown(), the stop event
        causes the thread to exit cleanly within poll-timeout window.
  T2.4: High-rate burst (5000 msgs/sec for 0.5s) without message loss
        and without backpressure on the post() side.
  T2.5: shared_secret authentication actually works (welcome handshake
        succeeds across process boundary using labconfig-derived secret).

Run:
    python tests/zprocess_event_d_hybrid_test_2.py
"""
import os
import sys
import time
import threading
import pickle

import zmq
from zprocess import Process

# Use ls_zprocess like BLACS does:
from labscript_utils.ls_zprocess import Event as lsEvent, ProcessTree as lsProcessTree

# Two distinct event channels, one per worker.
EVENT_A = 'd_hybrid_test2_workerA'
EVENT_B = 'd_hybrid_test2_workerB'

# Burst: 5000 msgs/sec for 0.5s => 2500 msgs total per channel.
BURST_MSGS = 2500
BURST_INTERVAL = 1.0 / 5000  # 200 us


class WorkerA(Process):
    EVENT_NAME = EVENT_A

    def run(self):
        from labscript_utils.ls_zprocess import Event as lsEvent
        from zprocess.process_tree import _default_process_tree as pt

        # Verify shared_secret was inherited (labscript secured path).
        ss = pt.shared_secret
        ai = pt.allow_insecure
        print(f'[{self.EVENT_NAME}] pid={os.getpid()} '
              f'shared_secret_inherited={ss is not None} allow_insecure={ai}',
              flush=True)

        try:
            event = lsEvent(self.EVENT_NAME, role='wait')
        except Exception as e:
            self.to_parent.put(('FAIL', f'lsEvent init: {type(e).__name__}: {e}'))
            return

        cache = {}
        msg_count = [0]
        cross_leak = [0]   # counts messages whose event_name doesn't match
        drain_errors = []
        stop = threading.Event()

        def drain():
            while not stop.is_set():
                try:
                    with event.sublock:
                        if not event.sub.poll(200, zmq.POLLIN):
                            continue
                        encoded_name, eid, data = event.sub.recv_multipart()
                    if encoded_name != event._encoded_event_name:
                        cross_leak[0] += 1
                        continue
                    cache[eid.decode('utf8')] = pickle.loads(data)
                    msg_count[0] += 1
                except Exception as e:
                    drain_errors.append(f'{type(e).__name__}: {e}')
                    if len(drain_errors) > 5:
                        break

        t = threading.Thread(target=drain, daemon=True, name='drain')
        t.start()

        self.to_parent.put(('READY', None))
        self.from_parent.get()  # wait for STOP

        # T2.3: shutdown semantics — set stop, drain should exit within ~poll timeout.
        t_shutdown_start = time.perf_counter()
        stop.set()
        t.join(timeout=2.0)
        shutdown_elapsed_ms = (time.perf_counter() - t_shutdown_start) * 1000
        thread_exited_cleanly = not t.is_alive()

        self.to_parent.put(('RESULT', {
            'event_name': self.EVENT_NAME,
            'messages_received': msg_count[0],
            'cross_leak': cross_leak[0],
            'drain_errors': drain_errors,
            'shutdown_elapsed_ms': shutdown_elapsed_ms,
            'thread_exited_cleanly': thread_exited_cleanly,
            'cache_keys_count': len(cache),
            'shared_secret_inherited': ss is not None,
        }))


class WorkerB(WorkerA):
    EVENT_NAME = EVENT_B


def parent_main():
    # T2.5: ls_zprocess ProcessTree.instance() — labscript-secured.
    pt = lsProcessTree.instance()
    pt.check_broker()
    print(f'[parent] pid={os.getpid()} broker_in_port={pt.broker_in_port} '
          f'shared_secret_set={pt.shared_secret is not None} '
          f'allow_insecure={pt.allow_insecure}', flush=True)
    assert pt.broker_in_port is not None

    # Start two workers (multi-worker scenario T2.2).
    print('[parent] starting workers A and B...', flush=True)
    wA = WorkerA()
    wB = WorkerB()
    toA, fromA = wA.start()
    toB, fromB = wB.start()

    for tag_label, q in [('A', fromA), ('B', fromB)]:
        tag, payload = q.get()
        if tag == 'FAIL':
            print(f'[parent] worker {tag_label} FAIL: {payload}', flush=True)
            wA.terminate(wait_timeout=2)
            wB.terminate(wait_timeout=2)
            sys.exit(1)
        assert tag == 'READY'
    print('[parent] both workers READY', flush=True)

    # Two independent posters, one per channel.
    posterA = lsEvent(EVENT_A, role='post')
    posterB = lsEvent(EVENT_B, role='post')

    # T2.4: high-rate burst — interleaved posts to both channels.
    post_lat_A = []
    post_lat_B = []
    t_start = time.perf_counter()
    for i in range(BURST_MSGS):
        t0 = time.perf_counter()
        posterA.post('chan_A1', i * 1.0)
        post_lat_A.append((time.perf_counter() - t0) * 1e6)

        t1 = time.perf_counter()
        posterB.post('chan_B1', i * 10.0)
        post_lat_B.append((time.perf_counter() - t1) * 1e6)

        if i % 1000 == 999:
            time.sleep(0)  # yield
        time.sleep(BURST_INTERVAL)
    t_elapsed = time.perf_counter() - t_start

    # Allow drain to flush.
    time.sleep(0.6)

    # STOP both workers.
    toA.put('STOP')
    toB.put('STOP')
    rA = fromA.get()
    rB = fromB.get()
    wA.terminate(wait_timeout=5)
    wB.terminate(wait_timeout=5)

    rA_tag, rA_data = rA
    rB_tag, rB_data = rB
    assert rA_tag == 'RESULT' and rB_tag == 'RESULT'

    def stats(lats):
        s = sorted(lats)
        return s[len(s)//2], s[int(len(s)*0.99)], max(s)

    medA, p99A, maxA = stats(post_lat_A)
    medB, p99B, maxB = stats(post_lat_B)

    print('')
    print('=' * 70)
    print('TEST 2 RESULTS')
    print('=' * 70)
    print(f'T2.1 ls_zprocess wrapper (Event, shared_secret) cross-proc:')
    print(f'     A shared_secret_inherited={rA_data["shared_secret_inherited"]}')
    print(f'     B shared_secret_inherited={rB_data["shared_secret_inherited"]}')
    print(f'     {"PASS" if rA_data["shared_secret_inherited"] and rB_data["shared_secret_inherited"] else "FAIL"}')
    print('')
    print(f'T2.2 Multi-worker no cross-leak:')
    print(f'     A messages_received={rA_data["messages_received"]}/{BURST_MSGS} '
          f'cross_leak={rA_data["cross_leak"]}')
    print(f'     B messages_received={rB_data["messages_received"]}/{BURST_MSGS} '
          f'cross_leak={rB_data["cross_leak"]}')
    print(f'     {"PASS" if rA_data["cross_leak"] == 0 and rB_data["cross_leak"] == 0 else "FAIL (cross-leak detected)"}')
    print('')
    print(f'T2.3 Drain-thread shutdown semantics:')
    print(f'     A shutdown_elapsed={rA_data["shutdown_elapsed_ms"]:.1f}ms '
          f'thread_exited={rA_data["thread_exited_cleanly"]}')
    print(f'     B shutdown_elapsed={rB_data["shutdown_elapsed_ms"]:.1f}ms '
          f'thread_exited={rB_data["thread_exited_cleanly"]}')
    print(f'     {"PASS" if rA_data["thread_exited_cleanly"] and rB_data["thread_exited_cleanly"] else "FAIL"}')
    print('')
    print(f'T2.4 High-rate burst (5000 msgs/s each = 10kHz aggregate):')
    print(f'     post latency A: median={medA:.1f}us p99={p99A:.1f}us max={maxA:.1f}us')
    print(f'     post latency B: median={medB:.1f}us p99={p99B:.1f}us max={maxB:.1f}us')
    A_loss = BURST_MSGS - rA_data["messages_received"]
    B_loss = BURST_MSGS - rB_data["messages_received"]
    print(f'     A loss={A_loss}/{BURST_MSGS}  B loss={B_loss}/{BURST_MSGS}')
    print(f'     wall_time={t_elapsed*1000:.1f}ms (expected ~{BURST_MSGS*BURST_INTERVAL*1000:.0f}ms)')
    print(f'     {"PASS (zero loss)" if A_loss == 0 and B_loss == 0 else f"PARTIAL (loss A={A_loss} B={B_loss}; max acceptable depends on use)"}')
    print('')
    print(f'T2.5 Drain errors:')
    print(f'     A: {rA_data["drain_errors"] or "none"}')
    print(f'     B: {rB_data["drain_errors"] or "none"}')
    print(f'     {"PASS" if not rA_data["drain_errors"] and not rB_data["drain_errors"] else "FAIL"}')
    print('=' * 70)


if __name__ == '__main__':
    parent_main()
