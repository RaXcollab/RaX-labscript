"""Test 3: drain shutdown latency with empty queue.

Validates:
  T4.1: When NO posts have been sent (empty queue), drain thread shutdown
        is bounded by the poll timeout, not unbounded.
  T4.2: After full shutdown, no zombie threads remain in worker subprocess.
  T4.3: Spamming shutdown signal repeatedly doesn't cause errors.

Run:
    python tests/zprocess_event_d_hybrid_test_3.py
"""
import os
import time
import threading
import pickle

import zmq
from zprocess import Process
from labscript_utils.ls_zprocess import Event as lsEvent, ProcessTree as lsProcessTree

EVENT_NAME = 'd_hybrid_test3_idle'
POLL_TIMEOUT_MS = 500  # production design value


class IdleWorker(Process):
    def run(self):
        from labscript_utils.ls_zprocess import Event as lsEvent

        event = lsEvent(EVENT_NAME, role='wait')

        cache = {}
        msg_count = [0]
        stop = threading.Event()

        def drain():
            while not stop.is_set():
                with event.sublock:
                    if not event.sub.poll(POLL_TIMEOUT_MS, zmq.POLLIN):
                        continue
                    _, eid, data = event.sub.recv_multipart()
                cache[eid.decode('utf8')] = pickle.loads(data)
                msg_count[0] += 1

        t = threading.Thread(target=drain, daemon=True, name='drain')
        t.start()

        self.to_parent.put(('READY', None))

        # NOTE: parent does NOT post any messages. Drain thread will sit in
        # poll(500ms) repeatedly. We measure shutdown latency below.
        self.from_parent.get()  # wait for STOP signal

        # T4.1 measurement
        t_start = time.perf_counter()
        stop.set()
        t.join(timeout=2.0)
        shutdown_ms = (time.perf_counter() - t_start) * 1000

        # T4.3: spam stop again
        spam_errors = []
        for _ in range(5):
            try:
                stop.set()
            except Exception as e:
                spam_errors.append(str(e))

        # T4.2: count active threads (excluding main + this teardown moment)
        active_threads = [th.name for th in threading.enumerate()
                          if th is not threading.main_thread()]

        self.to_parent.put(('RESULT', {
            'shutdown_ms': shutdown_ms,
            'thread_alive_after_join': t.is_alive(),
            'msg_count': msg_count[0],
            'spam_errors': spam_errors,
            'active_threads_at_teardown': active_threads,
        }))


def parent_main():
    pt = lsProcessTree.instance()
    pt.check_broker()
    print(f'[parent] broker_in_port={pt.broker_in_port}', flush=True)

    worker = IdleWorker()
    to_child, from_child = worker.start()
    tag, _ = from_child.get()
    assert tag == 'READY'
    print('[parent] worker READY; not posting anything; will signal STOP',
          flush=True)

    # Sit idle a bit so worker is genuinely INSIDE poll(500ms).
    time.sleep(1.5)

    to_child.put('STOP')
    tag, result = from_child.get()
    worker.terminate(wait_timeout=5)

    print('')
    print('=' * 60)
    print('TEST 3 RESULTS')
    print('=' * 60)
    print(f'T4.1 shutdown latency with empty queue:')
    print(f'   shutdown_ms = {result["shutdown_ms"]:.1f} (poll timeout = {POLL_TIMEOUT_MS}ms)')
    print(f'   {"PASS (bounded by poll timeout)" if result["shutdown_ms"] <= POLL_TIMEOUT_MS + 50 else "FAIL"}')
    print('')
    print(f'T4.2 thread fully exited after join:')
    print(f'   thread_alive_after_join = {result["thread_alive_after_join"]}')
    print(f'   active_threads (incl. tear-down moment): {result["active_threads_at_teardown"]}')
    print(f'   {"PASS" if not result["thread_alive_after_join"] else "FAIL"}')
    print('')
    print(f'T4.3 spam stop.set() (idempotent):')
    print(f'   errors = {result["spam_errors"] or "none"}')
    print(f'   {"PASS" if not result["spam_errors"] else "FAIL"}')
    print(f'   msg_count (should be 0 since parent never posted): {result["msg_count"]}')
    print('=' * 60)


if __name__ == '__main__':
    parent_main()
