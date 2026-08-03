These patterns address friction points in the BLACS base class that affect any RemoteControl-pattern device with ordering constraints or non-spinbox UI. See `notes/2026-02-22_BigSky_tab_redesign.html` for the full writeup.

**Problem 1: `program_manual` sends ALL values, not deltas.** The base class calls `get_front_panel_values()` on every change, then sends the full dict to the worker. For devices where re-sending an unchanged value has side effects (e.g., BigSky rejects mode changes while lamps are active), this causes silent failures.

**Pattern: `_last_sent_values` delta tracking (worker-side)**
```python
def init(self):
    super().init()
    self._last_sent_values = {}

def check_remote_values(self):
    # ... get remote_values ...
    self._last_sent_values.update(remote_values)  # seed from remote state
    return remote_values

def program_manual(self, front_panel_values):
    for connection, value in front_panel_values.items():
        if self._last_sent_values.get(connection) == value:
            continue  # skip unchanged
        # ... send value ...
        self._last_sent_values[connection] = value
```

**Problem 2: `check_remote_values` poll races with user input.** The 5s periodic poll returns stale values and overwrites AO objects via `_update_ao_widgets`. With spinboxes this is a brief flicker; with toggle buttons the revert is very visible and can cause the reverted value to be programmed to hardware.

**Pattern: `_recently_changed` cooldown (tab-side)**
```python
self._recently_changed = {}  # {connection: monotonic_timestamp}

def _on_toggle_clicked(self, connection, value):
    self._recently_changed[connection] = time.monotonic()
    self._AO[connection].set_value(value, program=True)

def _update_ao_widgets(self, connection, value):
    if time.monotonic() - self._recently_changed.get(connection, 0) < 10:
        return  # skip — user changed this recently, poll hasn't caught up
    # ... update widget ...
```
Set the cooldown to 2x the poll interval (default 5s → 10s cooldown).

**Problem 3: `transition_to_buffered` uses safe ordering, `program_manual` does not.** If your device has command ordering constraints (e.g., must be in standby before changing mode), implement ordering in `program_manual` or the worker, not just in `transition_to_buffered`.

**Custom `initialise_GUI` pattern:** Call `create_analog_outputs()` for ALL channels (BLACS needs AO objects for save/restore and `program_device`). Create standard widgets only for continuous values. Binary controls → toggle buttons. Mode selectors → combo boxes. Command-only channels → hidden (no widget). Custom widgets call `AO.set_value(value, program=True)`.

**Problem 4: `_fetch_initial_values` blindly accepts remote zeros after GUI restart.** The base class fetches remote values on startup and updates the front panel unconditionally. If the remote GUI has no config persistence and restarts with zeroed values, BLACS silently overwrites its saved state (which may contain correct setpoints from the last session).

**Active RemoteControl module is `user_devices.RemoteControl`** — the `labscript-devices/labscript_devices/RemoteControl/` copy is dead code on this machine. All citations below are to the userlib copy. (See `.claude/rules/devices.md`.)

**Per-shot monitor snapshot HDF5 layout.** `RemoteControlWorker` writes pre- and post-shot snapshots into `/data/{device}/monitor_values/{initial,final}_monitor_values`. **Full layout, semantics, and the history of the pre-2026-05-06 `initial==final` bug live in [`docs/shot-h5-layout.md`](shot-h5-layout.md).** Quick summary here for device authors:

- **⚠ ACTIVE BUG (found 2026-08-02): these datasets are currently not being written at all.** The worker cache stays empty in production (`initial_monitor_values: 0 channels` on every shot in BLACS.log) and the empty-initial gate ([blacs_workers.py:690](../userlib/user_devices/RemoteControl/blacs_workers.py#L690)) then skips both writes. Zero LaserLockGUI or RasteringGUI monitor_values found in any shot since 2026-05-07; BigSkyLasers wrote **initial-only** datasets (its initial bypasses the cache via REQ-REP) until 2026-07-22, none since. Do not rely on these datasets until fixed — details in `shot-h5-layout.md` "Known bugs", Bug B.
- Pre-snapshot taken in `transition_to_buffered` ([userlib/user_devices/RemoteControl/blacs_workers.py:676](../userlib/user_devices/RemoteControl/blacs_workers.py#L676)); post in `post_experiment` ([:693](../userlib/user_devices/RemoteControl/blacs_workers.py#L693)). Both write via `_save_monitor_values_to_hdf5` ([:714](../userlib/user_devices/RemoteControl/blacs_workers.py#L714), per-column `np.float64` since 2026-04-29; was `float32` before — see precision warning).
- **Both snapshots are `dict(self._pubsub_cache)` — no REQ-REP round-trip.** The tab forwards every PUB-SUB monitor value into the BLACS-internal EventBroker ([blacs_tabs.py:594](../userlib/user_devices/RemoteControl/blacs_tabs.py#L594)); the worker's daemon drain thread ([blacs_workers.py:462](../userlib/user_devices/RemoteControl/blacs_workers.py#L462)) writes it into `_pubsub_cache` keyed by connection. You get this for free by inheriting `RemoteControlWorker` — nothing to wire up per device. `check_all_remote_values()` ([:581](../userlib/user_devices/RemoteControl/blacs_workers.py#L581)) is no longer on this path.
- **Columns = the monitor connections that have published at least once**, not `child_connections`. Outputs get no column; a monitor topic that never appears in the stream gets no column at all (not 0.0, not NaN); an entirely empty cache writes no dataset ([:715](../userlib/user_devices/RemoteControl/blacs_workers.py#L715)).
- **Freshness caveat:** the snapshot is the newest cached sample, so it can lag a `PROGRAM_VALUE` issued moments earlier by up to one publish period — ~250 ms at the ~4 Hz BigSky/Rastering publish rate (HF_Locking runs at 10 Hz). Fine for the slow physical quantities these devices monitor; do not use these datasets for sub-100 ms causality.
- **The value is whatever that GUI publishes on that topic** — HF_Locking publishes `freq_display` (the wavemeter reading), BigSky per-parameter sensor readings, Rastering live stage coordinates. Check the publisher, not the `CHECK_VALUE` handler.
- **Override caveat (BigSkyWorker):** a subclass that overrides `transition_to_buffered` must take the snapshot itself. `RasteringWorker` does it right ([RasteringDevice/blacs_workers.py:264](../userlib/user_devices/RasteringDevice/blacs_workers.py#L264)); `BigSkyWorker` still uses `check_all_remote_values()` ([BigSkyHub/blacs_workers.py:403](../userlib/user_devices/BigSkyHub/blacs_workers.py#L403), [:459](../userlib/user_devices/BigSkyHub/blacs_workers.py#L459)) while inheriting the base `post_experiment`, so its initial and final datasets have different column sets and different meanings.

**Datasets are absent when:** `enable_comms=False`, no `remote_device_operation` group exists in the shot file, the PUB-SUB cache is empty (nothing published all session), or the shot was aborted (snapshots cleared by `abort_*` methods, [blacs_workers.py:733-741](../userlib/user_devices/RemoteControl/blacs_workers.py#L733)). See `shot-h5-layout.md` for full conditions.

**Pre-fix precision warning (shots before 2026-04-29):** snapshot dtype was `np.float32`, ULP ~40 MHz at 348 THz. Programmed setpoints in `remote_device_operation` are full float64 in all shots; only the `monitor_values` snapshots were affected.

**Pattern: startup mismatch dialog (tab-side override)**
```python
@define_state(MODE_MANUAL, True)
def _fetch_initial_values(self):
    remote_values = yield (
        self.queue_work(self.primary_worker, 'check_remote_values')
    )
    # Compare remote_values vs self._AO[connection].value
    # If mismatch > threshold: show QMessageBox, let user choose
    # "Use saved" → self._mark_initial_fetch_done(); self.program_device()
    # "Accept remote" → inmain(self._update_ao_widgets, remote_values)
```
Implemented in `LaserLockTab`. Consider for any RemoteControl device where the remote GUI lacks config persistence.

---

## BigSky "Keep Warm" Auto-Arm Pattern

`BigSkyWorker` uses `_is_armed` per prefix to skip re-arming between queued shots (avoids lamp cycling). `program_manual` guards warmup-controlled channels (lamps/shutter/qswitch/modes) when `_keep_warm` is active—only voltage passes through. Tab syncs AO values on toggle to prevent `program_device()` from undoing warmup state.

---

## BLACS Saved-State Resilience

When the connection table changes (devices added/removed, parameters changed), BLACS handles stale saved state gracefully. `FrontPanelSettings.check_row()` silently excludes channels no longer in the connection table. **No need to delete the saved state h5 file** after connection table changes.

## State Machine Event Ordering

Events queued by `@define_state` methods execute in FIFO order in the mainloop thread. The base class `DeviceTab.__init__` runs: `initialise_GUI()` → `restore_save_data()` → `initialise_workers()` → `program_device()`. Events queued during `initialise_workers` (like `connect_to_reqrep`) execute before `program_device`.

---

## Fork-Specific State Machine Extensions

This fork extends stock labscript BLACS with post-experiment states and a multi-worker `yield` API. The MODE bitmask (in `blacs/blacs/tab_base_classes.py:64`) is:

| Flag | Value | Meaning |
|---|---|---|
| `MODE_MANUAL` | 1 | Idle; user-driven |
| `MODE_TRANSITION_TO_BUFFERED` | 2 | T2B — preparing to run |
| `MODE_TRANSITION_TO_MANUAL` | 4 | T2M — tearing down to idle |
| `MODE_BUFFERED` | 8 | Shot executing |
| `MODE_TRANSITION_TO_POST_EXP` | **16** | **fork** — T2POST |
| `MODE_POST_EXP` | **32** | **fork** — between-shot idle in queue |

**Per-shot worker hook:** `post_experiment(notify_queue, program, skip_manual)` runs between BUFFERED and MANUAL (or between BUFFERED and the next T2B if queued). It is the canonical place for per-shot teardown (clearing latched lines, snapshotting final monitor values, fetching scope traces). `skip_manual=True` is set by `QueueManager` when more shots are queued — devices use this to defer expensive widget syncs.

**Back-compat fallback:** Worker classes that don't implement `post_experiment` trigger a ~80 ms first-shot probe per shot. Implement the hook to skip the probe.

**Multi-worker yield API:** A `@define_state` method can yield `([worker_task_1, worker_task_2, ...], check_main_first)` to fan out work to multiple workers in parallel and resume after all complete. The old single-task form `yield self.queue_work(...)` is still supported via the `old_worker_flow` branch in mainloop. Use multi-worker yield when programming several workers or dispatching a coordinated transition.

**`@define_state(allowed_modes=...)`** must include `MODE_POST_EXP` if the callback should run between queued shots — e.g. PUB-SUB monitor poll, BigSky auto-rearm checks. Omitting POST_EXP silently disables the callback in the queued-shot window.

---

## NI_DAQmx Output Worker Lifecycle

**Shared class warning:** `NI_DAQmxOutputWorker` is used by ALL NI devices (6361, 6535, etc.). Changes to `transition_to_buffered`, `post_experiment`, or `transition_to_manual` affect every NI device. Guard device-specific behavior with property checks (e.g., `if self._latched_lines:`).

### Queued-Shot Lifecycle (no transition_to_manual between shots)

```
Shot 1: transition_to_buffered → run → post_experiment
Shot 2: transition_to_buffered → run → post_experiment   ← NO transition_to_manual
...
Last:   transition_to_manual                              ← only here (or on abort)
```

**Consequence:** Per-shot cleanup (restoring latched channels, etc.) must go in `post_experiment`, not `transition_to_manual`. `transition_to_manual` is for queue-end and abort only.

**`program_manual` silent no-op:** After `post_experiment` clears tasks (`self.DO_task = None`), `program_manual` silently skips DO writes. Use `_ensure_manual_DO_task()` to create a temporary DO-only task when needed between queued shots.

### Latched Digital Output Pattern

Channels in `device_properties['latched_lines']` (set via `set_property` in connection table):
1. **Pre-latch** (`transition_to_buffered`): `_ensure_manual_DO_task()` → `program_manual(latch_values)` → `stop_tasks()` → hardware holds latched state
2. **Restore** (`post_experiment`): `_ensure_manual_DO_task()` → three-layer merge → `program_manual(restore)`
3. **Restore** (`transition_to_manual`): `start_manual_mode_tasks()` → three-layer merge → `program_manual(restore)`
4. **Three-layer merge**: `initial_values` (baseline) → `cached_final_values` (timed channels) → `initial_values` for latched channels only

### ZMQ REQ Socket Resilience

REQ sockets stuck in pending-recv after abort. Pattern: `_reset_socket()` closes and re-creates. Call between `stop_task()` and `start_task()` (thread-safe window). Always use `LINGER=0`. Store context as instance variable for reuse.

**Thread-safety for shared REQ sockets:** When a ZMQ REQ socket is used from multiple threads (e.g., DAQmx callback thread + BLACS worker thread), ALL send/recv pairs must be serialized with a lock. REQ enforces strict send-recv alternation; interleaved operations from two threads cause an unrecoverable EFSM error. Additionally, stop callback-producing tasks BEFORE using shared sockets from the worker thread — locking alone is not sufficient if the callback can fire between the worker's send and recv.

### Init-Order Safety

When making a method idempotent by adding cleanup at the top (e.g., `stop_tasks()` in `start_manual_mode_tasks()`), initialize all attributes the cleanup accesses BEFORE the first call. Example: `self.AO_task = None` and `self.DO_task = None` in `init()` before `start_manual_mode_tasks()`.
