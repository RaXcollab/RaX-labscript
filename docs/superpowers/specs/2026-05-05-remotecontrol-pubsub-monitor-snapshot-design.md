# RemoteControl PUB-SUB Monitor Snapshot — Design Spec

**Status:** Empirically validated. Ready for implementation.

**Date:** 2026-05-05 (validated 2026-05-05)

**Validation:** All load-bearing assumptions (A1, A2, A3, A4, A5, A6, A9, A10, A15) verified by tests in `tests/zprocess_event_d_hybrid_test{,_2,_3}.py` and `tests/qt_multi_slot_test.py`. Code-trace confirmed A7, A8, A11. See "Verification status" section.

## Context

The RemoteControl device family (LaserLockGUI, BigSkyHub, RasteringDevice) was originally designed to capture pre/post-shot snapshots of monitor (PUB-SUB measurement) data into `/data/{device}/monitor_values/{initial,final}_monitor_values` for downstream drift detection and analysis. Two distinct bugs prevent this from working:

1. **`monitor_values` was capturing the wrong thing.** The original implementation used REQ-REP `CHECK_VALUE` to populate the snapshot dict. For HF_Locking specifically, `CHECK_VALUE` returns the server-stored *setpoint*, not the wavemeter measurement. So `initial_monitor_values == final_monitor_values` for ~98% of shots in our scan data — pre-vs-post drift detection was impossible.
2. **The "shared dict" workaround in the working tree is broken across the process boundary.** The `pubsub_monitor_cache` dict passed via `init_kwargs` to the worker is pickled at subprocess spawn time. The worker holds a frozen copy that the tab's later cache updates never reach. (Empirically: in some shots the worker's frozen copy happens to have data from before pickling and writes that same value forever; in others it's empty and `_save_monitor_values_to_hdf5` silently writes nothing.)

The fix needs to:
- Carry the live PUB-SUB monitor values into the worker subprocess, where the snapshot is taken
- Be modular: handled in the base `RemoteControl` so all 3 subclasses inherit correct behavior with zero per-device cooperation
- Not slow down the shot loop (the brief mentions a PERF logging guard around `transition_to_buffered`)
- Use BLACS-idiomatic primitives where possible

## Architecture: D-hybrid modular

The tab subscribes to the external GUI's PUB-SUB (existing behavior, unchanged). On each incoming PUB-SUB message, it forwards the value as a `zprocess.Event` post into the BLACS-internal `EventBroker`. The worker subprocess subscribes to those internal Events via a daemon drain thread that maintains a worker-local cache. At shot boundaries, the worker snapshots the cache.

```
External GUI (HF_Locking, etc.) — PUB on its port
                       │ ZMQ PUB-SUB (existing)
                       ▼
        BLACS RemoteControlTab (Qt main + GUI thread)
        ─── single point of external contact ───
        On every incoming monitor message:
          1. existing GUI updates (unchanged)
          2. NEW: self._monitor_event.post(connection, value)
                       │
                       │ zprocess.Event PUSH (non-blocking)
                       ▼
        ProcessTree EventBroker (daemon thread in BLACS root)
        ─── existing zprocess infrastructure ───
                       │
                       │ XPUB fan-out
                       ▼
        Each RemoteControl worker subprocess
        ─── inherits broker info via parentinfo ───
        Daemon drain thread reads event.sub directly
        (bypasses event.wait()'s identifier filter)
        Updates self._pubsub_cache[connection] = value
                       │
                       │ on transition_to_buffered:
                       │   self.initial_monitor_values = dict(self._pubsub_cache)
                       │ on post_experiment:
                       │   self.final_monitor_values = dict(self._pubsub_cache)
                       ▼
        /data/{device}/monitor_values/{initial,final}_monitor_values
```

### Why this design

- **Tab is single point of external contact** — only the tab subscribes to the external GUI's PUB-SUB. Worker doesn't need to know external host/port.
- **Uses existing BLACS infrastructure** — `zprocess.EventBroker` already runs in every BLACS process tree. No new infrastructure.
- **Future-proof** — any other BLACS component (plugin, worker) that wants live monitor data can subscribe to `f'{device_name}_pubsub_monitor'` events without touching device code.
- **Zero subclass changes** — module-level `check_broker()` ensures broker is up before any worker spawns; signal-slot connection in inherited `connect_to_pubsub` ensures all subclasses get tab-side posting without overrides.
- **Correct semantics** — captures live PUB-SUB values, not server-stored setpoints. Pre/post snapshots can genuinely differ.
- **Performance** — replaces 22 REQ-REP round-trips/shot for BigSky (~1100ms saved) with a microsecond dict copy. Tab post is non-blocking.

### Why bypass `event.wait()` on the worker side

`event.wait(identifier, timeout)` filters by identifier and **drops** messages whose identifier doesn't match (verified by reading `process_tree.py:360-397`). For our streaming case where we want all channels' messages on one Event, we'd lose data on every wait call.

Bypassing wait() and reading `event.sub.recv_multipart()` directly receives all messages with our event_name. We still hold `event.sublock` for thread safety (matching wait()'s pattern). This is the only labscript usage of `event.sub` direct access — we'd be establishing the precedent.

## Implementation outline

### Constants

```python
# In RemoteControl/blacs_workers.py module top:
PUBSUB_DRAIN_POLL_TIMEOUT_MS = 500   # max shutdown latency, verified by Test 3
PUBSUB_SHUTDOWN_JOIN_TIMEOUT = 1.0   # seconds; daemon=True is the safety net
```

The event-name format is fixed: `f'{device_name}_pubsub_monitor'`. This namespaces per device so workers never see another device's traffic (verified Test 2 T2.2: zero cross-leak).

### `userlib/user_devices/RemoteControl/blacs_tabs.py`

**Module top** (after existing imports):
```python
from labscript_utils.ls_zprocess import ProcessTree, Event
# Ensure the BLACS-internal EventBroker is up before any worker subprocess spawns.
# check_broker() is idempotent (guards on broker_in_port is None), so safe to call
# from module-top across multiple import sites (LaserLock/BigSky/Rastering all import).
ProcessTree.instance().check_broker()
```

**In `RemoteControlTab.connect_to_pubsub` (extend existing method)**:
```python
def connect_to_pubsub(self):
    """Start (or restart) the heartbeat subscriber thread."""
    # Lazy-create the post-side Event ONCE per tab lifetime. The internal
    # EventBroker lives in the BLACS root process and only dies with BLACS, so
    # there is no legitimate reason to recreate the post Event on reconnect.
    # The hasattr guard is required: connecting the same slot twice causes
    # duplicate fires (verified Test 4 T3.4).
    if not hasattr(self, '_monitor_event'):
        self._monitor_event = Event(
            f'{self.device_name}_pubsub_monitor',
            role='post',
        )
        self._pubsub_bridge.monitor_value_received.connect(
            self._post_to_internal_broker
        )
    # ↓ existing reconnect logic unchanged ↓
    self._pubsub_stop_event.set()
    time.sleep(0.05)
    self._pubsub_stop_event.clear()
    self.pubsub_connected = False
    self._heartbeat_thread = threading.Thread(
        target=self._heartbeat_subscriber_loop, daemon=True
    )
    self._heartbeat_thread.start()
```

**New method `RemoteControlTab._post_to_internal_broker`**:
```python
def _post_to_internal_broker(self, connection, value_str):
    """Forward a PUB-SUB monitor value into the BLACS-internal EventBroker so
    worker subprocesses can subscribe. Runs on the GUI thread via Qt queued
    connection from the daemon subscriber thread that emits the bridge signal.

    Numeric-only contract: only values that float() parses are forwarded. If a
    future subclass needs to forward string-valued monitors, it must override
    this method. (Empirically all current devices are numeric: THz, V, A, °C,
    raster coords.)
    """
    try:
        value = float(value_str)
    except (ValueError, TypeError):
        return  # non-numeric, silently dropped per contract
    try:
        self._monitor_event.post(connection, value)
    except Exception as e:
        # post() should not fail (PUSH is non-blocking, broker is local).
        # Log loudly if it does so we notice broken plumbing.
        self.logger.error(f"_post_to_internal_broker: post failed for "
                          f"{connection}={value}: {type(e).__name__}: {e}")
```

**Tab-side cache `_pubsub_monitor_cache`** — KEEP. The existing `_on_monitor_value_received` writes to it for GUI monitor-label updates (`_update_monitor_widgets`). This is a separate concern from the worker's snapshot.

**Remove from `init_kwargs`** (line 222 of working tree) — delete the `"pubsub_monitor_cache": self._pubsub_monitor_cache,` entry. The worker no longer uses it.

### `userlib/user_devices/RemoteControl/blacs_workers.py`

**Module top**:
```python
import pickle
import threading
import zmq
from labscript_utils.ls_zprocess import Event

PUBSUB_DRAIN_POLL_TIMEOUT_MS = 500
PUBSUB_SHUTDOWN_JOIN_TIMEOUT = 1.0
```

**In `RemoteControlWorker.init` (extend existing)**:
```python
def init(self):
    # ↓ existing setup ↓
    ...
    # PUB-SUB monitor cache — populated by daemon drain thread.
    self._pubsub_cache = {}
    self._pubsub_stop = threading.Event()
    self._monitor_event = None
    self._pubsub_thread = None
    if self.child_monitor_connections:
        # All 4 tab classes (base + 3 subclasses) pass child_monitor_connections
        # via init_kwargs (verified by grep). Empty list is falsy, so devices
        # without monitor children skip the drain thread entirely.
        try:
            self._monitor_event = Event(
                f'{self.device_name}_pubsub_monitor',
                role='wait',
            )
        except TimeoutError as e:
            # Event() raises TimeoutError if it can't connect to the broker
            # within 5 seconds (zprocess.process_tree:334). Should not happen
            # in practice — broker is local and check_broker() ran at module
            # import. If it does, log loudly and continue without the cache;
            # the worker is still functional, just monitor_values won't populate.
            self.logger.error(
                f"PUB-SUB drain init failed (broker unreachable): {e}. "
                f"monitor_values will be empty for this worker session."
            )
            return
        self._pubsub_thread = threading.Thread(
            target=self._pubsub_drain_loop,
            daemon=True,
            name=f'{self.device_name}_pubsub_drain',
        )
        self._pubsub_thread.start()
        self.logger.info(
            f"PUB-SUB drain thread started for "
            f"{len(self.child_monitor_connections)} monitor channels"
        )
```

**New method `RemoteControlWorker._pubsub_drain_loop`**:
```python
def _pubsub_drain_loop(self):
    """Drain the BLACS-internal EventBroker into self._pubsub_cache.

    Bypasses event.wait()'s identifier filter (which discards messages with
    non-matching identifiers) so all monitor-channel messages on this Event
    are received. Verified empirically (Tests 1, 2): zero loss at 10 kHz
    aggregate, zero cross-leak between devices.
    """
    while not self._pubsub_stop.is_set():
        try:
            with self._monitor_event.sublock:
                if not self._monitor_event.sub.poll(
                    PUBSUB_DRAIN_POLL_TIMEOUT_MS, zmq.POLLIN
                ):
                    continue
                _, event_id, data = self._monitor_event.sub.recv_multipart()
            self._pubsub_cache[event_id.decode('utf8')] = pickle.loads(data)
        except zmq.ContextTerminated:
            # Socket is dead (process shutting down). Exit cleanly.
            return
        except (ValueError, pickle.UnpicklingError) as e:
            # Malformed message — log and keep draining.
            self.logger.warning(
                f"_pubsub_drain_loop: malformed message: {type(e).__name__}: {e}"
            )
        except Exception as e:
            # Unexpected — log and back off to avoid tight error loop.
            self.logger.error(
                f"_pubsub_drain_loop: {type(e).__name__}: {e}", exc_info=True
            )
            time.sleep(1.0)
```

**In `RemoteControlWorker.transition_to_buffered`** — replace:
```python
self.initial_monitor_values = dict(getattr(self, 'pubsub_monitor_cache', {}))
```
with:
```python
# dict() copy is atomic under GIL; thread-safe vs drain thread's per-key writes.
self.initial_monitor_values = dict(self._pubsub_cache)
self.logger.info(
    f"initial_monitor_values: {len(self.initial_monitor_values)} channels"
)
```

**In `RemoteControlWorker.post_experiment`** — same swap for `final_monitor_values`, with matching `info`-level log.

**In `RemoteControlWorker.shutdown` (extend)**:
```python
def shutdown(self):
    # Stop drain thread first so no further cache writes happen during teardown.
    self._pubsub_stop.set()
    if self._pubsub_thread is not None:
        # daemon=True guarantees process exit even if join times out.
        self._pubsub_thread.join(timeout=PUBSUB_SHUTDOWN_JOIN_TIMEOUT)
    # ↓ existing close logic ↓
    ...
```

### Behavioral guarantees of the drain thread

- **Lifetime**: starts in `init()`, ends when `_pubsub_stop` is set in `shutdown()` OR when subprocess exits (daemon=True).
- **Thread-safety of cache**: drain thread does per-key writes (`cache[k] = v`); main worker thread does `dict(cache)` snapshots. Both are atomic under Python's GIL — no lock needed.
- **Shutdown latency**: bounded by `PUBSUB_DRAIN_POLL_TIMEOUT_MS` (500ms). Empirically 6.9ms in idle case (Test 3). 13ms in active case (Test 2 T2.3).
- **No reconnect logic**: the BLACS-internal EventBroker only dies with the BLACS root process; if it dies, all workers die too.

### Subclass changes

**None.** LaserLockTab, BigSkyTab, RasteringTab, and their workers all inherit corrected behavior automatically.

### Files NOT touched

- `LaserLockDevice/blacs_tabs.py`, `LaserLockDevice/labscript_devices.py`
- `BigSkyHub/blacs_tabs.py`, `BigSkyHub/blacs_workers.py`, `BigSkyHub/labscript_devices.py`
- `RasteringDevice/blacs_tabs.py`, `RasteringDevice/labscript_devices.py`
- All other RemoteControl-derived devices

### Migration steps (concrete diff plan)

1. **`RemoteControl/blacs_tabs.py:222`** — delete the line `"pubsub_monitor_cache": self._pubsub_monitor_cache,` from the `init_kwargs` dict.
2. **`RemoteControl/blacs_tabs.py`** — add module-top imports + `check_broker()` call (described above).
3. **`RemoteControl/blacs_tabs.py:287`** — extend `connect_to_pubsub` with the lazy-create block at top.
4. **`RemoteControl/blacs_tabs.py`** — add `_post_to_internal_broker` method (anywhere in class).
5. **`RemoteControl/blacs_workers.py`** — add module-top imports + constants.
6. **`RemoteControl/blacs_workers.py:init`** — extend with cache + Event + drain thread.
7. **`RemoteControl/blacs_workers.py`** — add `_pubsub_drain_loop` method.
8. **`RemoteControl/blacs_workers.py:358`** — change `dict(getattr(self, 'pubsub_monitor_cache', {}))` → `dict(self._pubsub_cache)` and add log line.
9. **`RemoteControl/blacs_workers.py:370`** — same swap for `final_monitor_values`.
10. **`RemoteControl/blacs_workers.py:shutdown`** — extend with stop + join.
11. **`RasteringDevice/blacs_tabs.py:321`** — delete the same `"pubsub_monitor_cache": ...` line (Rastering tab has its own copy from before the base-class promotion).
12. **`RasteringDevice/blacs_workers.py:85`** — change `dict(self.pubsub_monitor_cache)` → `dict(self._pubsub_cache)` (or remove the override entirely and let the base handle it — see "Out of scope" below).

The RasteringDevice's existing `transition_to_buffered`/`post_experiment` overrides can be cleaned up in a separate PR (they re-implement what the base now does correctly), but that cleanup is out of scope for this design.

### Logging plan

| Where | Level | What |
|---|---|---|
| Worker `init` | `info` | "PUB-SUB drain thread started for {N} monitor channels" (only if drain thread starts) |
| Worker drain loop | `warning` | malformed message exceptions |
| Worker drain loop | `error` | unexpected exceptions (with exc_info) |
| Worker `transition_to_buffered` | `info` | "initial_monitor_values: {N} channels" |
| Worker `post_experiment` | `info` | "final_monitor_values: {N} channels" |
| Tab `_post_to_internal_broker` | `error` | only if `event.post()` raises (should never happen) |

This is enough to detect the failure mode "cache stays empty" (info logs would show 0 channels) without spamming on healthy operation.

## Verification status

All testable items validated as of 2026-05-05. Test files in `tests/`.

| # | Assumption | Status | Evidence |
|---|---|---|---|
| **A1** | Module-level `check_broker()` starts broker | ✅ PASS | Test 1 — broker bound to port before subprocess spawn |
| **A2** | parentinfo carries `broker_in_port` to subprocess | ✅ PASS | Test 1 — worker saw same port as parent |
| **A3** | Worker `Event(role='wait')` connects cross-process | ✅ PASS | Test 1 — welcome handshake succeeded |
| **A4** | `event.sub.recv_multipart()` bypasses identifier filter | ✅ PASS | Test 1 (600/600) + Test 2 (5000/5000) — all distinct identifiers received, last-write-wins values exact |
| **A5** | `event.sublock` during long `poll()` is safe | ✅ PASS | Tests 1, 2 — 0 drain errors |
| **A6** | Qt `pyqtSignal` multi-slot fires both, cross-thread | ✅ PASS | Test 4 — both slots fire on GUI thread; double-`connect()` causes duplicate fire (confirms `hasattr` guard required) |
| **A7** | `connect_to_pubsub` not overridden by subclasses | ✅ PASS | Code-trace — only one definition (`RemoteControl/blacs_tabs.py:287`) |
| **A8** | `_pubsub_bridge` exists before `connect_to_pubsub` runs | ✅ PASS | Code-trace — all 3 subclasses create bridge in `initialise_GUI`, which BLACS calls before `initialise_workers` → `connect_to_remote` → `connect_to_pubsub` |
| **A9** | PUSH socket post is non-blocking at normal rates | ✅ PASS at production rates | Test 1 (600 Hz): median 110µs, p99 216µs, max 273µs. Test 4 (saturation): median stays 16µs, but p99.9 = 55ms and max = 125ms when the broker buffer fills. **Production rate is ~150 msgs/sec aggregate, 50x below the saturation regime — A9 holds.** |
| **A10** | Worker daemon thread doesn't leak | ✅ PASS | Test 2 T2.3 (clean exit 13ms) + Test 3 T4.2 (no zombie threads) |
| **A11** | `pubsub_monitor_cache` has no consumers outside this scope | ✅ PASS | Code-trace — 7 usages, all within plumbing being replaced |
| **A12** | `PERF transition_to_buffered` not regressed | ⏸ post-impl | Real BLACS shot required; cache snapshot is µs vs ~1100ms REQ-REP — unlikely regression |
| **A13** | Mock mode no regression | ⏸ post-impl | Cache stays empty in mock → `_save_monitor_values_to_hdf5` early-returns (same as today) |
| **A14** | `event.sub` API stays stable | ⏸ accept | `sub` is public (no underscore), zprocess API-stable for years |
| **A15** | EventBroker handles our message rate | ✅ PASS | Test 2 T2.4 — 10 kHz aggregate, zero loss, post latency 16-63µs |
| **A16** | First-shot sparse cache acceptable | ⏸ accept | Documented limitation — slow-joiner before subscriber init, welcome handshake protects after |
| **A17** | `dict()` snapshot thread-safe | ⏸ accept | Standard Python GIL guarantee |
| **idempotency** | `check_broker()` safe to call from multiple import sites | ✅ PASS | Code-read — guards on `broker_in_port is None` |
| **welcome packet protocol** | No risk of single-frame welcome leaking into 3-frame `recv_multipart()` | ✅ PASS | Code-read — broker only sends welcomes for `WELCOME_MESSAGE`-prefixed subscriptions; event-name subs don't generate welcomes |
| **ls_zprocess wrapper** | Same flow works through labscript-secured `ls_zprocess.Event` | ✅ PASS | Test 2 T2.1 — `shared_secret` inherited cross-process |
| **multi-worker isolation** | Workers with different event names don't cross-leak | ✅ PASS | Test 2 T2.2 — zero cross-leak between two workers |
| **shutdown latency bound** | Drain shutdown bounded by poll timeout, not unbounded | ✅ PASS | Test 3 T4.1 — 6.9ms idle, 13ms active, both well under 500ms bound |
| **PUSH ceiling under saturation** | Behavior at 100k-msg sustained burst | ✅ characterised | Test 4 — zero loss at 100k msgs, but p99.9 latency 55ms and max 125ms when post() blocks on full buffer. Not a concern at our 150 msgs/sec production rate. |
| **`self.logger` on tab** | Attribute exists for logging | ✅ PASS | Code-trace — `RemoteControl/blacs_tabs.py:270,273,404` |
| **`self.logger` on worker** | Attribute exists for logging | ✅ PASS | Code-trace — set at `RemoteControl/blacs_workers.py:32` |
| **Event init failure handled** | `TimeoutError` from broker unreachable doesn't crash worker | ✅ Designed | Try/except in `init()` logs error and continues; cache stays empty (graceful degradation) |
| **No other RemoteControl subclasses** | Only the 3 known classes inherit | ✅ PASS | Code-trace — only LaserLockTab/RasteringTab/BigSkyTab + LaserLockWorker/RasteringWorker/BigSkyWorker |
| **`restart_worker` lifecycle** | Tab restart kills+spawns fresh worker | ✅ PASS | `tab_base_classes.py:683` — full restart; new worker has empty cache (consistent with A16) |
| **Shutdown mid-shot race** | Worker `shutdown()` doesn't fire during in-flight `transition_to_buffered` | ✅ accept | BLACS state machine guarantees this: `shutdown()` is invoked only after the state queue is drained. Per-key dict writes vs `dict()` snapshot are GIL-atomic; even with overlap, last-millisecond miss is acceptable. |

Test files:
- `tests/zprocess_event_d_hybrid_test.py` — A1, A2, A3, A4, A5, A9
- `tests/zprocess_event_d_hybrid_test_2.py` — ls_zprocess wrapper, A10, A15, multi-worker
- `tests/zprocess_event_d_hybrid_test_3.py` — empty-queue shutdown latency
- `tests/zprocess_event_d_hybrid_test_4.py` — PUSH stress / backpressure ceiling
- `tests/qt_multi_slot_test.py` — A6

## Verification plan (post-implementation)

1. **Implementation diff matches "Migration steps" exactly** — review against the 12-step list before commit.
2. **Live shot test on real BLACS** — start BLACS with all three RemoteControl devices active, take a single shot, verify acceptance criteria below.
3. **Performance check**: `PERF transition_to_buffered` log line should show <100ms median for BigSky.
4. **Negative test**: disable one device's external GUI mid-scan, confirm worker doesn't crash and other devices keep working.

### Acceptance criteria (live BLACS shot)

| Device | Group must exist | Columns must be | Initial vs final |
|---|---|---|---|
| LaserLockGUI | `/data/LaserLockGUI/monitor_values/initial_monitor_values` and `final_monitor_values` | `('4', '6')` (TiSa_1_Value, TiSa_2_Value) | Both numeric float64; values within ±5 MHz of the shot's setpoint; `final - initial` non-zero in ≥80% of shots (lock noise) |
| BigSkyLasers | same path | The 10 RemoteAnalogMonitor children | Both numeric float64; `final - initial` shows physical drift (typically <1% of full-scale) |
| RasteringGUI | same path | `('laser_raster_x_coord_monitor', 'laser_raster_y_coord_monitor')` | Both numeric float64; equal in static-position mode, differ in scan mode |

If any device's group is **missing** in the h5 (cache empty at snapshot time), that's a regression. The expected behavior is the group exists and is non-empty. Note: A16 documents that the first shot after BLACS startup may have a sparse cache — re-run after a few seconds of warmup.

### Acceptance criteria (performance)

`PERF transition_to_buffered` log line should show:
- BigSky: <100ms median over 10-shot scan (was ~1100ms with REQ-REP)
- LaserLockGUI: <50ms median (was ~150ms)
- RasteringGUI: unchanged (was already cache-based)

### Acceptance criteria (logs)

Worker logs at `info` level should show:
```
PUB-SUB drain thread started for {N} monitor channels
... (during shot) ...
initial_monitor_values: {N} channels
... (after shot) ...
final_monitor_values: {N} channels
```

`{N}` should match the device's number of monitor children. If 0, the cache is empty — investigate.

## Behavioral change notes (for users / docs)

- `monitor_values` columns will now be **only the channels that the external GUI's PUB-SUB actually emits** — in practice, this is the `child_monitor_connections` (RemoteAnalogMonitor children), because that's what each external GUI is configured to publish. Output channels' setpoints remain in `/devices/{device}/remote_device_operation` (script-set) and `/front_panel/front_panel` (BLACS-state).
- The dtype is constructed dynamically from the cache keys at snapshot time by `_save_monitor_values_to_hdf5`. dtype is `np.float64` for all columns (fixed in `RemoteControl/blacs_workers.py:374` earlier this session).
- **Comparison with old broken behavior**: pre-fix, `_save_monitor_values_to_hdf5` either silently no-op'd (cache empty) or wrote stale snapshot values (cache pickled at spawn time). Post-fix, the cache reflects live PUB-SUB. The dtype.names are the same set of channels in both cases, but post-fix they actually contain measurement data.
- For LaserLockGUI: `monitor_values` columns will be `('4', '6')` (TiSa_1_Value and TiSa_2_Value) — Vexlum (`'3'`) drops from the snapshot since it has no monitor child.
- For BigSky: monitor_values columns will be the 10 RemoteAnalogMonitor children (`*_monitor` suffix). The 18 outputs drop from monitor_values; their setpoints remain in remote_device_operation and front_panel.
- For Rastering: `monitor_values` columns will be `('laser_raster_x_coord_monitor', 'laser_raster_y_coord_monitor')` — the 2 monitors. The 2 outputs drop from monitor_values.
- Old shots are not affected. Past `monitor_values` data should be re-interpreted per `docs/shot-h5-layout.md`.

## Out of scope

- Cleanup of RasteringDevice's `transition_to_buffered`/`post_experiment` overrides (they should be removed once base is correct, but separate PR).
- Adding wavemeter readings for output-only channels like Vexlum (would require adding RemoteAnalogMonitor children in connection table).
- Mock mode improvements (currently no `monitor_values` in mock — out of scope).
- Remote workers (RemoteProcessClient) — should work but not validated.
