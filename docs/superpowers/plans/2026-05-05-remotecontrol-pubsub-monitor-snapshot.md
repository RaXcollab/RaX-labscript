# RemoteControl PUB-SUB Monitor Snapshot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `RemoteControlWorker` snapshot the live PUB-SUB monitor cache (instead of a frozen pickled dict) so that `/data/{device}/monitor_values/{initial,final}_monitor_values` reflects real wavemeter / sensor / motor readings.

**Architecture:** "D-hybrid modular" — the BLACS RemoteControlTab forwards each PUB-SUB monitor message into a per-device `zprocess.Event` posted to the BLACS-internal `EventBroker`. Each worker subprocess runs a daemon drain thread that receives those Events and updates a worker-local `dict`. At shot boundaries, the worker calls `dict(self._pubsub_cache)` for an atomic snapshot. All three subclasses (LaserLockGUI, BigSkyHub, RasteringDevice) inherit the fix from the base — zero subclass code changes.

**Tech Stack:** Python 3.11, `zprocess` (1.x), `labscript_utils.ls_zprocess`, PyQt5 (via `qtutils.qt`), pyzmq 23.2, h5py, numpy 1.26. Custom forks of blacs/labscript-devices/labscript-utils per CLAUDE.md.

**Spec:** [docs/superpowers/specs/2026-05-05-remotecontrol-pubsub-monitor-snapshot-design.md](../specs/2026-05-05-remotecontrol-pubsub-monitor-snapshot-design.md)

**Empirical validation:** Tests in `tests/zprocess_event_d_hybrid_test{,_2,_3,_4}.py` and `tests/qt_multi_slot_test.py` validated the cross-process Event flow, ls_zprocess wrapper, multi-worker isolation, drain-thread shutdown, PUSH backpressure, and Qt multi-slot semantics. Design is verified before implementation.

**Test strategy note:** This codebase has no pytest harness for BLACS device classes (Qt + state machine + zprocess subprocesses make it impractical to unit-test). The standard verification is **(a) Python import smoke test** to catch syntax errors, and **(b) live BLACS shot** to verify integration. Each task ends with an import smoke test where applicable. The full integration check is Task 13 (live BLACS shot with concrete acceptance criteria).

**Conda activation:** Every `python` command MUST be prefixed with conda activation per CLAUDE.md:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python ...
```

---

## File Structure

| File | Role | Touched in tasks |
|---|---|---|
| `userlib/user_devices/RemoteControl/blacs_workers.py` | Base worker. Adds cache + drain thread + shutdown extension. Swaps `pubsub_monitor_cache` reads to `_pubsub_cache`. | 1, 2, 3, 4, 5, 6 |
| `userlib/user_devices/RemoteControl/blacs_tabs.py` | Base tab. Adds module-top `check_broker()`, lazy-creates post-side `Event`, forwards monitor values via new `_post_to_internal_broker` slot. Removes `pubsub_monitor_cache` from `init_kwargs`. | 7, 8, 9, 10 |
| `userlib/user_devices/RasteringDevice/blacs_tabs.py` | Subclass tab. Removes legacy `pubsub_monitor_cache` from its own `init_kwargs` (the subclass has its own copy from before base-class promotion). | 11 |
| `userlib/user_devices/RasteringDevice/blacs_workers.py` | Subclass worker. Swaps `self.pubsub_monitor_cache` → `self._pubsub_cache` in its `transition_to_buffered` override. | 12 |
| _none_ | Live BLACS shot acceptance check. | 13 |

**Files explicitly NOT touched:** `LaserLockDevice/*`, `BigSkyHub/*`, `NI_SCOPE/*`, `edge_counter/*`, all backend repos. The fix is fully inherited.

---

## Task 1: Worker — module-top imports + constants

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_workers.py:1-8`

- [ ] **Step 1: Add imports + constants at module top**

Replace the existing import block (lines 1-9) with:

```python
import time
import threading
import pickle

from blacs.tab_base_classes import Worker
import numpy as np
import labscript_utils.h5_lock
import h5py
import zmq
import json

from labscript_utils.ls_zprocess import Event

# PUB-SUB monitor cache constants (see design spec Tasks 1, 2, 3, 6).
PUBSUB_DRAIN_POLL_TIMEOUT_MS = 500   # max idle shutdown latency
PUBSUB_SHUTDOWN_JOIN_TIMEOUT = 1.0   # seconds; daemon=True is the safety net
```

- [ ] **Step 2: Smoke test — file imports without error**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RemoteControl import blacs_workers; print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_workers.py
git commit -m "RemoteControl: add ls_zprocess + threading imports for PUB-SUB drain"
```

---

## Task 2: Worker — extend `init()` with cache + drain thread

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_workers.py:215-230` (the `RemoteControlWorker.init` method)

- [ ] **Step 1: Replace the existing `init()` body with the extended version**

The existing `init()` is:
```python
def init(self):
    self.enable_comms = True
    self.h5_filepath = None
    self.child_connections = self.child_output_connections + self.child_monitor_connections

    self.remote_comms = RemoteCommunication(
        host=self.host,
        port=self.port,
        logger=self.logger,
        child_connections=self.child_connections,
        mock=self.mock,
    )

    self._initial_fetch_done = False
    self.initial_monitor_values = {}
    self.final_monitor_values = {}
```

Replace with:
```python
def init(self):
    self.enable_comms = True
    self.h5_filepath = None
    self.child_connections = self.child_output_connections + self.child_monitor_connections

    self.remote_comms = RemoteCommunication(
        host=self.host,
        port=self.port,
        logger=self.logger,
        child_connections=self.child_connections,
        mock=self.mock,
    )

    self._initial_fetch_done = False
    self.initial_monitor_values = {}
    self.final_monitor_values = {}

    # PUB-SUB monitor cache — populated by daemon drain thread.
    # All 4 tab classes (base + 3 subclasses) pass child_monitor_connections
    # via init_kwargs (verified by grep). Empty list is falsy, so devices
    # without monitor children skip the drain thread entirely.
    self._pubsub_cache = {}
    self._pubsub_stop = threading.Event()
    self._monitor_event = None
    self._pubsub_thread = None
    if self.child_monitor_connections:
        try:
            self._monitor_event = Event(
                f'{self.device_name}_pubsub_monitor',
                role='wait',
            )
        except TimeoutError as e:
            # Event() raises TimeoutError if it can't connect to the broker
            # within 5 seconds (zprocess.process_tree:334). Should not happen
            # in practice — broker is local and check_broker() ran at module
            # import time. If it does, log and continue without the cache;
            # the worker is still functional, monitor_values just stay empty.
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

- [ ] **Step 2: Smoke test — module still imports**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RemoteControl import blacs_workers; print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_workers.py
git commit -m "RemoteControl: spawn PUB-SUB drain thread in worker init"
```

---

## Task 3: Worker — add `_pubsub_drain_loop` method

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_workers.py` — add a new method on `RemoteControlWorker`

- [ ] **Step 1: Add the drain loop method**

Insert immediately after the `init()` method (i.e., before `def connect_to_remote(self)` at line 232):

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
                f"_pubsub_drain_loop: malformed message: "
                f"{type(e).__name__}: {e}"
            )
        except Exception as e:
            # Unexpected — log and back off to avoid a tight error loop.
            self.logger.error(
                f"_pubsub_drain_loop: {type(e).__name__}: {e}",
                exc_info=True,
            )
            time.sleep(1.0)
```

- [ ] **Step 2: Smoke test — method is callable**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RemoteControl.blacs_workers import RemoteControlWorker; assert callable(RemoteControlWorker._pubsub_drain_loop); print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_workers.py
git commit -m "RemoteControl: add _pubsub_drain_loop with classified error handling"
```

---

## Task 4: Worker — swap `transition_to_buffered` to use new cache

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_workers.py:358`

- [ ] **Step 1: Replace the snapshot line**

Current code at line 358 reads:
```python
            self.initial_monitor_values = dict(getattr(self, 'pubsub_monitor_cache', {}))
```

Replace with:
```python
            # dict() copy is atomic under the GIL; thread-safe vs the drain
            # thread's per-key writes. No lock needed.
            self.initial_monitor_values = dict(self._pubsub_cache)
            self.logger.info(
                f"initial_monitor_values: "
                f"{len(self.initial_monitor_values)} channels"
            )
```

- [ ] **Step 2: Smoke test — module still imports**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RemoteControl import blacs_workers; print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_workers.py
git commit -m "RemoteControl: snapshot initial_monitor_values from live drain cache"
```

---

## Task 5: Worker — swap `post_experiment` to use new cache

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_workers.py:370`

- [ ] **Step 1: Replace the final snapshot line**

Current code at line 370 reads:
```python
                self.final_monitor_values = dict(getattr(self, 'pubsub_monitor_cache', {}))
```

Replace with:
```python
                self.final_monitor_values = dict(self._pubsub_cache)
                self.logger.info(
                    f"final_monitor_values: "
                    f"{len(self.final_monitor_values)} channels"
                )
```

- [ ] **Step 2: Smoke test — module still imports**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RemoteControl import blacs_workers; print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_workers.py
git commit -m "RemoteControl: snapshot final_monitor_values from live drain cache"
```

---

## Task 6: Worker — extend `shutdown()` with stop + join

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_workers.py:416-417`

- [ ] **Step 1: Replace the 2-line shutdown body**

Current code at lines 416-417:
```python
def shutdown(self):
    self.remote_comms.shutdown()
```

Replace with:
```python
def shutdown(self):
    # Stop drain thread first so no further cache writes happen during
    # teardown. daemon=True guarantees process exit even if join times out.
    self._pubsub_stop.set()
    if self._pubsub_thread is not None:
        self._pubsub_thread.join(timeout=PUBSUB_SHUTDOWN_JOIN_TIMEOUT)
    self.remote_comms.shutdown()
```

- [ ] **Step 2: Smoke test — module still imports**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RemoteControl import blacs_workers; print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_workers.py
git commit -m "RemoteControl: stop and join PUB-SUB drain thread in worker shutdown"
```

---

## Task 7: Tab — module-top imports + `check_broker()`

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_tabs.py:1-15`

- [ ] **Step 1: Add ls_zprocess imports + check_broker call**

Replace the existing import block (lines 1-15) with:

```python
from qtutils.qt import QtWidgets, QtGui, QtCore
from qtutils import inmain

from blacs.device_base_class import (
    DeviceTab,
    define_state,
    MODE_BUFFERED,
    MODE_MANUAL,
    MODE_TRANSITION_TO_BUFFERED,
    MODE_TRANSITION_TO_MANUAL,
)

import threading
import zmq
import time

from labscript_utils.ls_zprocess import ProcessTree, Event

# Ensure the BLACS-internal EventBroker is up before any worker subprocess
# spawns. check_broker() is idempotent (guards on broker_in_port is None),
# so this is safe to call from module-top across multiple import sites
# (LaserLock/BigSky/Rastering all import this module).
ProcessTree.instance().check_broker()
```

- [ ] **Step 2: Smoke test — module imports and broker is up**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "
from user_devices.RemoteControl import blacs_tabs
from labscript_utils.ls_zprocess import ProcessTree
pt = ProcessTree.instance()
assert pt.broker_in_port is not None, 'broker not started'
print(f'ok broker_in_port={pt.broker_in_port}')
"
```
Expected stdout begins with `ok broker_in_port=` and a port number.

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_tabs.py
git commit -m "RemoteControl: ensure EventBroker is up at tab-module import time"
```

---

## Task 8: Tab — add `_post_to_internal_broker` method

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_tabs.py` — add new method on `RemoteControlTab`

- [ ] **Step 1: Add the slot method**

Insert immediately after `_on_monitor_value_received` (current line 485-499 region — find the line `self.logger.debug(f"Monitor update error for {connection}: {e}")` and add after the method ends, before the `# ── GUI status management ──` comment line):

```python
    def _post_to_internal_broker(self, connection, value_str):
        """Forward a PUB-SUB monitor value into the BLACS-internal
        EventBroker so worker subprocesses can subscribe.

        Runs on the GUI thread via Qt queued connection from the daemon
        subscriber thread that emits ``_pubsub_bridge.monitor_value_received``.

        Numeric-only contract: only values that float() parses are forwarded.
        If a future subclass needs to forward string-valued monitors, it
        must override this method. (Empirically all current devices are
        numeric: THz, V, A, deg C, raster coords.)
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
            self.logger.error(
                f"_post_to_internal_broker: post failed for "
                f"{connection}={value}: {type(e).__name__}: {e}"
            )
```

- [ ] **Step 2: Smoke test — method is callable**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RemoteControl.blacs_tabs import RemoteControlTab; assert callable(RemoteControlTab._post_to_internal_broker); print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_tabs.py
git commit -m "RemoteControl: add _post_to_internal_broker tab slot for monitor forward"
```

---

## Task 9: Tab — extend `connect_to_pubsub` with lazy-create

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_tabs.py:287-298` (existing `connect_to_pubsub` method)

- [ ] **Step 1: Add the lazy-create block at the top of `connect_to_pubsub`**

Current method body:
```python
def connect_to_pubsub(self):
    """Start (or restart) the heartbeat subscriber thread."""
    # Signal any existing threads to stop
    self._pubsub_stop_event.set()
    time.sleep(0.05)  # give them a moment
    self._pubsub_stop_event.clear()
    self.pubsub_connected = False

    self._heartbeat_thread = threading.Thread(
        target=self._heartbeat_subscriber_loop, daemon=True
    )
    self._heartbeat_thread.start()
```

Replace with:
```python
def connect_to_pubsub(self):
    """Start (or restart) the heartbeat subscriber thread."""
    # Lazy-create the post-side Event ONCE per tab lifetime. The internal
    # EventBroker lives in the BLACS root process and only dies with BLACS,
    # so there is no legitimate reason to recreate the post Event on
    # reconnect. The hasattr guard is required: connecting the same Qt
    # slot twice causes duplicate fires (verified Test 4 T3.4).
    if not hasattr(self, '_monitor_event'):
        self._monitor_event = Event(
            f'{self.device_name}_pubsub_monitor',
            role='post',
        )
        self._pubsub_bridge.monitor_value_received.connect(
            self._post_to_internal_broker
        )

    # Signal any existing threads to stop
    self._pubsub_stop_event.set()
    time.sleep(0.05)  # give them a moment
    self._pubsub_stop_event.clear()
    self.pubsub_connected = False

    self._heartbeat_thread = threading.Thread(
        target=self._heartbeat_subscriber_loop, daemon=True
    )
    self._heartbeat_thread.start()
```

- [ ] **Step 2: Smoke test — module imports**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RemoteControl import blacs_tabs; print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_tabs.py
git commit -m "RemoteControl: lazy-create post-Event and connect slot in connect_to_pubsub"
```

---

## Task 10: Tab — remove `pubsub_monitor_cache` from `init_kwargs`

**Files:**
- Modify: `userlib/user_devices/RemoteControl/blacs_tabs.py:222`

- [ ] **Step 1: Delete the obsolete `init_kwargs` line**

Delete line 222 of the current file (inside `initialise_workers`). The line to remove is:
```python
                "pubsub_monitor_cache": self._pubsub_monitor_cache,
```

The surrounding `create_worker(...)` call after the deletion should look like:
```python
def initialise_workers(self):
    self.create_worker(
        "main_worker",
        "user_devices.RemoteControl.blacs_workers.RemoteControlWorker",
        {
            "mock": self.mock,
            "host": self.host,
            "port": self.reqrep_port,
            "child_output_connections": self.child_output_connections,
            "child_monitor_connections": self.child_monitor_connections,
        },
    )
    self.primary_worker = "main_worker"
```

The tab-side `self._pubsub_monitor_cache` dict (initialised in `initialise_GUI`) is intentionally KEPT — `_on_monitor_value_received` still writes to it for the GUI's monitor-label updates via `_update_monitor_widgets`.

- [ ] **Step 2: Smoke test — module imports**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RemoteControl import blacs_tabs; print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RemoteControl/blacs_tabs.py
git commit -m "RemoteControl: drop pickled pubsub_monitor_cache from worker init_kwargs"
```

---

## Task 11: RasteringDevice tab — remove `pubsub_monitor_cache` from `init_kwargs`

**Files:**
- Modify: `userlib/user_devices/RasteringDevice/blacs_tabs.py:321`

- [ ] **Step 1: Delete the duplicate `init_kwargs` line**

The RasteringTab has its OWN copy of the line (from before the base-class promotion). Delete line 321:
```python
                "pubsub_monitor_cache": self._pubsub_monitor_cache,
```

The surrounding `create_worker(...)` call after the deletion should look like:
```python
def initialise_workers(self):
    self.create_worker(
        "main_worker",
        "user_devices.RasteringDevice.blacs_workers.RasteringWorker",
        {
            "mock": self.mock,
            "host": self.host,
            "port": self.reqrep_port,
            "child_output_connections": self.child_output_connections,
            "child_monitor_connections": self.child_monitor_connections,
        },
    )
    self.primary_worker = "main_worker"
```

- [ ] **Step 2: Smoke test — module imports**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RasteringDevice import blacs_tabs; print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RasteringDevice/blacs_tabs.py
git commit -m "Rastering: drop pickled pubsub_monitor_cache from worker init_kwargs"
```

---

## Task 12: RasteringWorker — swap `pubsub_monitor_cache` to `_pubsub_cache` in override

**Files:**
- Modify: `userlib/user_devices/RasteringDevice/blacs_workers.py:85`

- [ ] **Step 1: Update the snapshot line in the override**

Current code at line 85:
```python
        self.initial_monitor_values = dict(self.pubsub_monitor_cache)
```

Replace with:
```python
        # dict() copy is atomic under the GIL. The cache is populated by the
        # base RemoteControlWorker's drain thread (see Task 2-3 of the design).
        self.initial_monitor_values = dict(self._pubsub_cache)
        self.logger.info(
            f"initial_monitor_values: "
            f"{len(self.initial_monitor_values)} channels"
        )
```

NOTE: `RasteringWorker.transition_to_buffered` overrides the base. It does NOT override `post_experiment`, so the base's `post_experiment` (already swapped in Task 5) is used.

- [ ] **Step 2: Smoke test — module imports**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "from user_devices.RasteringDevice import blacs_workers; print('ok')"
```
Expected stdout: `ok`

- [ ] **Step 3: Commit**

```bash
git add userlib/user_devices/RasteringDevice/blacs_workers.py
git commit -m "Rastering: snapshot from live drain cache in transition_to_buffered override"
```

---

## Task 13: Live BLACS shot — acceptance criteria

**Files:**
- Inspect (read-only): `C:\Users\radmo\MIT Dropbox\Shungo Fukaya\Experiments\Main_Experiment\<YYYY>\<MM>\<DD>\` — fresh shot h5
- Inspect (read-only): `logs/BLACS.log`

This task verifies integration of all prior changes against a real BLACS instance and a real PUB-SUB stream. There are no code changes here — this is the pass/fail gate before declaring the work done.

- [ ] **Step 1: Compile a smoke sequence**

In RunManager, open and compile any sequence in `userlib/labscriptlib/Main_Experiment/sequences/` that uses LaserLockGUI, BigSkyHub, and RasteringDevice (e.g., `Closed_cell.py`). Verify the connection table compiles without errors. If RunManager reports an error, fix the underlying device-class issue before continuing.

- [ ] **Step 2: Restart BLACS**

Close BLACS, then re-launch via the lab's standard startup. Wait until all device tabs have transitioned past the orange "initialising" state.

- [ ] **Step 3: Verify drain-thread startup logs**

Open `logs/BLACS.log` and look for these `INFO` lines (one per RemoteControl device with monitor children):

```
PUB-SUB drain thread started for 2 monitor channels   # LaserLockGUI
PUB-SUB drain thread started for 10 monitor channels  # BigSkyLasers
PUB-SUB drain thread started for 2 monitor channels   # RasteringGUI
```

If any of these are MISSING for an active device, that's a regression — investigate before continuing. If you see "PUB-SUB drain init failed" log lines, the broker is unreachable; check the Task 7 module-top `check_broker()` call ran.

- [ ] **Step 4: Wait for cache to fill**

Wait at least 5 seconds after BLACS startup so each external GUI has published at least one round of PUB-SUB monitor values. (Per A16 in the spec, the first shot after startup may otherwise have a sparse cache.)

- [ ] **Step 5: Take a single shot**

Engage RunManager and queue one shot. Wait for it to complete and produce an h5 in `C:\Users\radmo\MIT Dropbox\Shungo Fukaya\Experiments\Main_Experiment\<YYYY>\<MM>\<DD>\<HHMM>\`.

- [ ] **Step 6: Inspect the h5 file with HDFView (or h5py)**

Run:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "
import h5py, glob, os
# Adjust path if necessary
files = sorted(glob.glob(r'C:\\Users\\radmo\\MIT Dropbox\\Shungo Fukaya\\Experiments\\Main_Experiment\\**\\*.h5', recursive=True), key=os.path.getmtime)
latest = files[-1]
print('Inspecting:', latest)
with h5py.File(latest, 'r') as f:
    for dev in ['LaserLockGUI', 'BigSkyLasers', 'RasteringGUI']:
        path = f'/data/{dev}/monitor_values'
        if path not in f:
            print(f'  {dev}: GROUP MISSING (regression)')
            continue
        g = f[path]
        for ds_name in ['initial_monitor_values', 'final_monitor_values']:
            if ds_name not in g:
                print(f'  {dev}/{ds_name}: MISSING')
                continue
            ds = g[ds_name]
            print(f'  {dev}/{ds_name}: dtype.names={ds.dtype.names} values={ds[0]}')
"
```

Expected output: every device shows `initial_monitor_values` and `final_monitor_values` with the column lists from the spec's acceptance criteria:

| Device | dtype.names |
|---|---|
| LaserLockGUI | `('4', '6')` |
| BigSkyLasers | The 10 RemoteAnalogMonitor children (`*_monitor` suffix) |
| RasteringGUI | `('laser_raster_x_coord_monitor', 'laser_raster_y_coord_monitor')` |

If any group is `MISSING`, the cache failed to fill — investigate before declaring done.

- [ ] **Step 7: Verify init vs final differ (drift detection works)**

For LaserLockGUI specifically (the regression that triggered this work): compare `initial_monitor_values` and `final_monitor_values`. They should differ by lock-noise scale (~10 Hz to ~5 MHz at THz scale). If they're bit-identical, CHECK_VALUE-style stale data is leaking — investigate.

For BigSky and Rastering, expect small physical drift between init and final (motor/temperature settle).

- [ ] **Step 8: Verify performance — `PERF transition_to_buffered`**

Grep `logs/BLACS.log` for the most recent shot's PERF lines:

```
PERF transition_to_buffered: <X> ms
```

Expected:
- BigSky: < 100 ms median over a 10-shot scan (was ~1100 ms with REQ-REP)
- LaserLockGUI: < 50 ms median (was ~150 ms)
- RasteringGUI: unchanged from current behaviour

If BigSky is still in the hundreds-of-ms regime, something is calling `check_all_remote_values()` instead of using the cache — revisit Tasks 4 and 5.

- [ ] **Step 9: Negative test — disconnect one external GUI mid-scan**

While a multi-shot scan is running, kill one external GUI process (e.g., HF_Locking). Verify:
- BLACS does NOT crash
- The killed device's tab transitions to "disconnected" state but other devices keep functioning
- After the scan completes, restart the killed GUI and verify the drain thread resumes receiving values (per A16, first post-restart shot may be sparse)

- [ ] **Step 10: Final sign-off**

If all of Steps 3-9 pass, the implementation is complete and correct. Push commits to the user-facing repo on the `RaXcollab/RaX-labscript` remote per CLAUDE.md (do NOT push without confirming with the user first — see "NEVER push without asking").

If any step fails, do NOT push. File a bug note in the session log with the specific symptom, then debug. The most likely failure modes are documented in the design spec's "Verification status" table.

---

## Self-Review

**Spec coverage:**
- Migration step 1 (delete tab init_kwargs) → Task 10 ✅
- Migration step 2 (tab module-top check_broker) → Task 7 ✅
- Migration step 3 (extend connect_to_pubsub) → Task 9 ✅
- Migration step 4 (add _post_to_internal_broker) → Task 8 ✅
- Migration step 5 (worker imports + constants) → Task 1 ✅
- Migration step 6 (extend worker init) → Task 2 ✅
- Migration step 7 (add _pubsub_drain_loop) → Task 3 ✅
- Migration step 8 (worker transition_to_buffered swap) → Task 4 ✅
- Migration step 9 (worker post_experiment swap) → Task 5 ✅
- Migration step 10 (worker shutdown extend) → Task 6 ✅
- Migration step 11 (Rastering tab init_kwargs) → Task 11 ✅
- Migration step 12 (Rastering worker swap) → Task 12 ✅
- Acceptance criteria (live shot) → Task 13 ✅
- All 12 spec migration steps + acceptance criteria are covered.

**Placeholder scan:** No `TBD`, `TODO`, "implement later", or "add appropriate error handling" left. All code blocks are complete.

**Type/name consistency check:**
- `_pubsub_cache` (worker dict) — used in Tasks 2, 3, 4, 5, 12 — same name everywhere ✅
- `_pubsub_stop` (worker threading.Event) — Tasks 2, 3, 6 — same name ✅
- `_pubsub_thread` (worker threading.Thread) — Tasks 2, 6 — same name ✅
- `_monitor_event` (worker Event) — Tasks 2, 3 — same name ✅
- `_monitor_event` (tab Event) — Tasks 8, 9 — same name (different attribute on different class — fine because they live on different objects) ✅
- `PUBSUB_DRAIN_POLL_TIMEOUT_MS` — Tasks 1, 3 — consistent ✅
- `PUBSUB_SHUTDOWN_JOIN_TIMEOUT` — Tasks 1, 6 — consistent ✅
- Event name format `f'{device_name}_pubsub_monitor'` — Tasks 2 (worker, role='wait') and 9 (tab, role='post') — must match: ✅ verified

**Order check:** Worker before tab is fine — the changes are in different files; the running BLACS doesn't see partial changes until restart at Task 13.

**Risk:** Between Task 10 and Task 13, the tab no longer passes `pubsub_monitor_cache` in `init_kwargs`. The base worker no longer reads it (Tasks 4, 5 swapped to `_pubsub_cache`). The Rastering worker still reads `self.pubsub_monitor_cache` UNTIL Task 12 lands. So if BLACS were restarted between Task 11 and Task 12, RasteringWorker would `AttributeError`. Mitigation: do Tasks 11 and 12 together (back-to-back) or ensure no BLACS restart between them. Not a correctness issue, just an ordering hazard for the implementer.
