"""Test 4: PUSH socket backpressure ceiling.

Test 1 verified 600 msgs/sec (no loss, sub-ms latency).
Test 2 verified 10 kHz aggregate (no loss).
This test pushes the rate up by 10x to characterize the actual ceiling
where backpressure or message loss becomes detectable.

Validates:
  T5.1: Sustained 100 kHz post() rate (10x our verified bound).
  T5.2: Loss percentage at saturation.
  T5.3: post() latency distribution under saturation.
"""
import os, time, threading, pickle
import zmq
from zprocess import Process
from labscript_utils.ls_zprocess import Event as lsEvent, ProcessTree as lsProcessTree

EVENT_NAME = 'd_hybrid_test4_stress'
NPOSTS = 100_000  # at 100 kHz target = 1 second of work


class StressWorker(Process):
    def run(self):
        from labscript_utils.ls_zprocess import Event as lsEvent
        event = lsEvent(EVENT_NAME, role='wait')
        cache = {}
        msg_count = [0]
        max_id_seen = [-1]
        stop = threading.Event()

        def drain():
            while not stop.is_set():
                with event.sublock:
                    if not event.sub.poll(100, zmq.POLLIN):
                        continue
                    _, eid, data = event.sub.recv_multipart()
                eid_str = eid.decode('utf8')
                cache[eid_str] = pickle.loads(data)
                msg_count[0] += 1
                try:
                    n = int(eid_str)
                    if n > max_id_seen[0]:
                        max_id_seen[0] = n
                except ValueError:
                    pass

        t = threading.Thread(target=drain, daemon=True)
        t.start()
        self.to_parent.put(('READY', None))
        self.from_parent.get()
        # let any tail messages drain
        time.sleep(1.0)
        stop.set()
        t.join(timeout=2.0)

        self.to_parent.put(('RESULT', {
            'received': msg_count[0],
            'unique_keys': len(cache),
            'max_id_seen': max_id_seen[0],
        }))


def parent_main():
    pt = lsProcessTree.instance()
    pt.check_broker()
    print(f'[parent] broker_in_port={pt.broker_in_port}', flush=True)

    worker = StressWorker()
    to_child, from_child = worker.start()
    tag, _ = from_child.get()
    assert tag == 'READY'
    print('[parent] worker READY; entering 100 kHz stress phase', flush=True)

    poster = lsEvent(EVENT_NAME, role='post')
    latencies = []

    # Send NPOSTS messages as fast as possible (no sleep between posts).
    t_start = time.perf_counter()
    for i in range(NPOSTS):
        t0 = time.perf_counter()
        poster.post(str(i), float(i))
        latencies.append((time.perf_counter() - t0) * 1e6)
    t_elapsed = time.perf_counter() - t_start

    actual_rate_khz = NPOSTS / t_elapsed / 1000

    # Allow drain to flush.
    time.sleep(2.0)

    to_child.put('STOP')
    tag, result = from_child.get()
    worker.terminate(wait_timeout=5)

    s = sorted(latencies)
    median_us = s[NPOSTS // 2]
    p99_us = s[int(NPOSTS * 0.99)]
    p999_us = s[int(NPOSTS * 0.999)]
    max_us = max(s)
    loss = NPOSTS - result['received']
    loss_pct = 100.0 * loss / NPOSTS

    print('')
    print('=' * 70)
    print('TEST 4 RESULTS — PUSH backpressure ceiling')
    print('=' * 70)
    print(f'Posted {NPOSTS:,} messages in {t_elapsed*1000:.1f}ms')
    print(f'Actual post rate: {actual_rate_khz:.1f} kHz')
    print(f'')
    print(f'T5.1 sustained rate:')
    print(f'   {"PASS (>=100 kHz)" if actual_rate_khz >= 100 else f"INFO ({actual_rate_khz:.1f} kHz observed; system-limited)"}')
    print(f'')
    print(f'T5.2 message loss at saturation:')
    print(f'   received={result["received"]:,}/{NPOSTS:,} loss={loss:,} ({loss_pct:.3f}%)')
    print(f'   unique_keys={result["unique_keys"]:,}, max_id_seen={result["max_id_seen"]}')
    print(f'   {"PASS (zero loss)" if loss == 0 else f"INFO (lost {loss} = {loss_pct:.3f}%)"}')
    print(f'')
    print(f'T5.3 post() latency under saturation:')
    print(f'   median={median_us:.1f}us p99={p99_us:.1f}us p99.9={p999_us:.1f}us max={max_us:.1f}us')
    print(f'   {"PASS (median <1ms)" if median_us < 1000 else "FAIL (latency degraded)"}')
    print('=' * 70)


if __name__ == '__main__':
    parent_main()
