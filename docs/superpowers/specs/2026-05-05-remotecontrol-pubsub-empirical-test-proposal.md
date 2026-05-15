# Empirical Test Proposal — Validate D-hybrid PUB-SUB Cross-Process Flow

**Companion to:** `2026-05-05-remotecontrol-pubsub-monitor-snapshot-design.md`

**Purpose:** Before implementing the design, validate the load-bearing assumptions A1, A2, A3, A4, A5, A9 from the design spec by running a minimal standalone reproduction of the cross-process Event flow. The goal is to catch any wrong assumptions in 10 minutes of testing rather than 4 hours of implementation + debugging.

## What we're testing (assumption → expected outcome)

| Assumption | Test sub-goal | Pass criterion |
|---|---|---|
| **A1** | Module-level `check_broker()` actually starts the broker before subprocess spawn | Subprocess can connect to parent's broker and receive messages |
| **A2** | parentinfo carries broker_in_port to subprocess | Subprocess's `process_tree.broker_in_port` is non-None |
| **A3** | Worker subprocess `Event(role='wait')` connects to parent's broker (not its own local one) | Messages posted by parent are received by subprocess |
| **A4** | `event.sub.recv_multipart()` bypassing wait() returns 3-frame structure with all messages regardless of identifier | Subscriber receives messages with multiple distinct identifiers, none discarded |
| **A5** | Holding `event.sublock` during long poll() doesn't break anything | Drain loop runs continuously without errors |
| **A9** | PUSH socket post is non-blocking under our message rate | Parent posts at 100 Hz for 5 seconds without blocking GUI-thread-equivalent timing |

## Test architecture

```
┌─ parent.py (BLACS-root analog) ──────────────────────────┐
│  Module level:                                           │
│    check_broker()  ← validates A1                        │
│  Main:                                                   │
│    spawn worker subprocess (zprocess.Process)            │
│    sleep 0.5s for worker to start                        │
│    create Event(role='post')                             │
│    for i in 200:  # 100 Hz × 2 sec                       │
│      event.post('chan_A', i * 1.0)                       │
│      event.post('chan_B', i * 2.0)                       │
│      event.post('chan_C', i * 3.0)                       │
│      sleep(0.005)                                        │
│    sleep 0.5s for worker to drain                        │
│    send 'STOP' via stdin or another Event                │
│    join worker, print results                            │
│                                                          │
│  Validates:                                              │
│    - A9: post() doesn't block (measure post() latency)   │
└──────────────────────────────────────────────────────────┘

┌─ worker.py (worker-subprocess analog) ──────────────────┐
│  Receives parentinfo via env var (zprocess auto)         │
│  At init:                                                │
│    print process_tree.broker_in_port  ← validates A2     │
│    create Event(role='wait')                             │
│    print "Event init succeeded"  ← validates A3 partial  │
│    cache = {}                                            │
│    spawn drain thread:                                   │
│      while not stop:                                     │
│        with event.sublock:                               │
│          if not event.sub.poll(500, zmq.POLLIN):         │
│            continue                                      │
│          _, eid, data = event.sub.recv_multipart()       │
│        cache[eid.decode()] = pickle.loads(data)          │
│        message_count += 1                                │
│  After STOP signal:                                      │
│    print message_count, len(cache), keys, last values    │
│                                                          │
│  Validates:                                              │
│    - A2: broker_in_port non-None                         │
│    - A3: messages from parent actually arrive            │
│    - A4: all 3 distinct identifiers received             │
│    - A5: drain loop runs without errors                  │
└──────────────────────────────────────────────────────────┘
```

## Implementation details

### File: `tests/zprocess_event_d_hybrid_test.py`

Single file with both parent and worker roles, dispatched by argv. Standalone — no labscript dependencies, just zprocess and stdlib.

```python
# Pseudocode — actual implementation will be ~80 lines

import sys, os, time, threading, pickle
import zmq
from zprocess import Process, ProcessTree
from zprocess.process_tree import _default_process_tree

# ---- Module-level: validate A1 ----
# Only run check_broker in parent (subprocess inherits broker info)
if 'WORKER_ROLE' not in os.environ:
    _default_process_tree.check_broker()
    print(f'[parent module] broker_in_port={_default_process_tree.broker_in_port}')

EVENT_NAME = 'd_hybrid_test_monitor'

class WorkerProc(Process):
    def run(self):
        from zprocess.process_tree import _default_process_tree as pt
        # ---- A2: broker_in_port should be non-None (inherited) ----
        print(f'[worker] broker_in_port={pt.broker_in_port}')
        assert pt.broker_in_port is not None, 'A2 FAILED: no broker info inherited'
        
        # ---- A3: Event(role='wait') connects to parent's broker ----
        from zprocess import Event
        event = Event(EVENT_NAME, role='wait')
        print('[worker] Event init succeeded')
        
        cache = {}
        msg_count = [0]
        stop = threading.Event()
        
        def drain():
            while not stop.is_set():
                try:
                    # ---- A5: hold sublock during long poll() ----
                    with event.sublock:
                        if not event.sub.poll(500, zmq.POLLIN):
                            continue
                        # ---- A4: bypass wait(), recv_multipart directly ----
                        _, eid, data = event.sub.recv_multipart()
                    cache[eid.decode()] = pickle.loads(data)
                    msg_count[0] += 1
                except Exception as e:
                    print(f'[worker drain] ERR: {e}')
                    time.sleep(0.5)
        
        t = threading.Thread(target=drain, daemon=True)
        t.start()
        
        # Wait for parent's STOP signal (received via stdin)
        sys.stdin.readline()
        stop.set()
        time.sleep(0.6)
        
        # ---- Report results ----
        print(f'[worker RESULT] messages_received={msg_count[0]}')
        print(f'[worker RESULT] cache_keys={sorted(cache.keys())}')
        print(f'[worker RESULT] cache_values={cache}')


def parent_main():
    print('[parent] starting worker subprocess')
    worker = WorkerProc()
    worker.start()
    time.sleep(0.5)  # let worker init Event + drain thread + welcome handshake
    
    from zprocess import Event
    event = Event(EVENT_NAME, role='post')
    print(f'[parent] Event(role=post) created; posting...')
    
    # ---- A9: measure post() latency ----
    post_latencies = []
    NPOSTS = 200  # 100 Hz × 2 sec
    for i in range(NPOSTS):
        t0 = time.perf_counter()
        event.post('chan_A', i * 1.0)
        event.post('chan_B', i * 2.0)
        event.post('chan_C', i * 3.0)
        post_latencies.append((time.perf_counter() - t0) * 1e6)  # microseconds
        time.sleep(0.005)  # 200 Hz of triple-posts = 600 msgs/sec
    
    time.sleep(0.5)  # drain time
    
    print(f'[parent] post latency: median={sorted(post_latencies)[NPOSTS//2]:.1f}us '
          f'max={max(post_latencies):.1f}us')
    print(f'[parent] sending STOP to worker')
    worker.process.stdin.write(b'STOP\n'); worker.process.stdin.flush()
    worker.terminate(wait_timeout=5)
    print('[parent] done')


if __name__ == '__main__':
    if 'WORKER_ROLE' in os.environ:
        # zprocess invokes the Process subclass automatically; we shouldn't reach here
        pass
    else:
        parent_main()
```

(Note: this is sketch-pseudocode. Actual zprocess.Process startup may differ slightly — the test will be filled in with the right zprocess invocation pattern.)

## Expected output (PASS)

```
[parent module] broker_in_port=<some_port>
[parent] starting worker subprocess
[worker] broker_in_port=<same_port>           ← A2 passes
[worker] Event init succeeded                  ← A3 partial
[parent] Event(role=post) created; posting...
[parent] post latency: median=20us max=300us  ← A9 passes (low latency)
[parent] sending STOP to worker
[worker RESULT] messages_received=600          ← A3 + A4 + A5 pass (all 600 received)
[worker RESULT] cache_keys=['chan_A', 'chan_B', 'chan_C']  ← A4 confirms 3 distinct
[worker RESULT] cache_values={'chan_A': 199.0, 'chan_B': 398.0, 'chan_C': 597.0}  ← A4 last-wins
[parent] done
```

## Failure modes to catch

| Failure | Symptom | What it tells us |
|---|---|---|
| Worker can't connect to broker | `[worker] broker_in_port=None` or Event init raises TimeoutError | **A1 or A2 fails** — module-level check_broker doesn't fire in parent before subprocess spawn. Need different approach (e.g., explicit check_broker in initialise_workers). |
| Worker connects but receives no messages | `messages_received=0` | **A3 fails** — broker is started but worker isn't actually subscribed to parent's broker. Possibly two separate brokers running. |
| Worker receives only some channels | `cache_keys=['chan_A']` (missing chan_B, chan_C) | **A4 fails** — bypassing wait() doesn't actually get all messages. Some other filtering somewhere. |
| Drain loop deadlocks or errors | `[worker drain] ERR: ...` | **A5 fails** — sublock contention or exception. |
| Post latency >1ms | `post latency median=2000us` | **A9 fails** — PUSH socket is blocking on us. Need NOBLOCK or LINGER tuning. |
| Worker receives messages but `len(cache) < 3` after run | partial results | Race condition in receive loop or cache update. |

## How to run

```bash
# From the labscript-suite root, in conda env
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript
cd c:/Users/radmo/labscript-suite
python tests/zprocess_event_d_hybrid_test.py
```

Expected runtime: ~5 seconds.

## What this test does NOT validate

- **A6** (Qt signals multi-slot): standalone test has no Qt — will validate by reading Qt docs / quick PyQt test if needed.
- **A7** (`connect_to_pubsub` truly inherited unchanged): code-trace, not test.
- **A8** (`_pubsub_bridge` exists before `connect_to_pubsub`): code-trace, not test.
- **A11–A17**: trivial / accepted.

So a successful empirical test takes us from ~70% confidence to ~90% confidence. The remaining gap is the BLACS-specific Qt + tab-init-order assumptions, which are best validated by an actual BLACS run on a real device after implementation.

## Decision point after the test

- **All assertions pass**: write the design doc as final, proceed to implementation plan.
- **A1/A2/A3 fails**: the broker-mediation approach has a fundamental issue we missed. Fall back to **Option A** (worker subscribes external PUB-SUB directly), which doesn't depend on broker setup ordering.
- **A4 fails**: bypassing wait() doesn't work — fall back to **D1** (one Event per channel), which uses the wait() API as intended.
- **A5 or A9 fails**: design is recoverable but needs adjustment (e.g., shorter poll timeout, NOBLOCK posts, sublock-free reads).

## Estimated effort

- Writing the test: ~15 minutes
- Running and analyzing: ~5 minutes
- If all passes: continue to design finalization
- If any fails: ~30 minutes to adjust approach and re-test

Total: ~30-50 minutes of investigation to validate or invalidate the design before committing implementation effort.

## Approval checkpoint

Before running the test, confirm the test plan above is what you want me to verify. Adjust scope if needed (e.g., add a 4th identifier, change post rate, add a deliberate stall to test recovery).
