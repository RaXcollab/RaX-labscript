# Device Internals

## labscript device registration mechanism
- `Device.__init__` writes `builtins.__dict__[name] = self` + appends to `compiler.inventory`
- `compiler.reset()` clears both between compiles
- RunManager globals also via `builtins.__dict__` (same mechanism)
- Key files: `labscript/compiler.py`, `labscript/base.py`, `runmanager/batch_compiler.py`

## BigSkyHub disconnect resilience (Feb 2026)
- Worker: "laser disconnected" → skip with warning (mirrors "unknown connection" pattern)
- Tab: per-laser PUB-SUB health tracking — groups start OFFLINE, 30s stale → gray out
- `transition_to_buffered` intentionally NOT guarded — disconnected laser during shot should abort

## BigSkyHub Keep Warm / Auto Re-Arm (Mar 2026)
- Worker: auto-arm in `transition_to_buffered` (stop → ext lamp mode → QS internal → lamps → shutter → qswitch)
- `transition_to_manual`: resets `_is_armed` flags only — no hardware commands
- **Auto Keep Warm**: tab-side PUB-SUB temp monitoring with hysteresis (trigger <37°C, reset ≥39°C). Tab calls `_send_keep_warm_warmup` → worker `restore_warmup_from_tab` → `_restore_warmup`. Stale-event guard prevents firing if unchecked while queued.
- **GUI sync**: Tab syncs Auto Keep Warm state to external GUI via `sync_keep_warm_to_gui` → ZMQ `keep_warm` command. GUI has matching hysteresis logic for standalone operation.
- `_is_armed` per prefix + `_verify_armed_state()` CHECK_VALUE verification before skip-rearm
- Tab: Stop/Warmup/Arm Ext action buttons dispatch via `queue_work(worker, 'send_action', ...)`
- "Auto Arm Ext" checkbox sets flag only — does NOT send hardware commands
- Fire-and-forget channels (warmup, start_lasing, stop) are in `_COMMAND_SUFFIXES` — skipped by `program_manual`. Must use `queue_work`/`send_action` for direct dispatch from tab buttons.
- **ZMQ error handling rule**: user-initiated actions (button clicks) must handle timeouts gracefully (log warning, don't raise). Shot-critical paths (`_arm_laser`, `_send_cmd`) should raise.
- Tab persists via `get_save_data`; remember-only on restart (no auto-fire)
- **Q-switch mode: always 0 (internal).** Mode 2 (external) requires delay generator we don't have.

## BLACS Fork Specifics (shafinulh/blacs)
- **`post_experiment` state**: Our fork adds `post_experiment(skip_manual)` between buffered and manual modes.
  - `skip_manual=True`: more shots in queue → worker `post_experiment()` runs (saves monitors), tab does NOT call `transition_to_manual`. Laser stays armed.
  - `skip_manual=False`: last shot or pause → worker `post_experiment()` runs, then tab calls `transition_to_manual`.
  - Workers that don't implement `post_experiment` fall back to `transition_to_manual` (backwards compat, ~80ms overhead on first shot).
  - Key file: `blacs/device_base_class.py` lines 769-837
- **Pause behavior**: When queue is paused, queue manager calls `transition_to_manual` on all MODE_POST_EXP devices. There is NO way for a device to distinguish pause from queue-end in `transition_to_manual`. Devices that need to stay armed through pauses must handle this themselves (e.g., BigSky temperature-conditional restore).
- **Connection table does NOT have access to RunManager globals** unless explicitly configured in BLACS preferences (fragile, not recommended). Hardcode hardware config in connection_table.py.

## BLACS AO Widget Internals
- AnalogOutput widgets have a `_label` attribute (QLabel) that can be hidden: `widget._label.hide()`
- Useful when widget is inside a group box that already provides label context

## NI_DAQmx Latched Digital Outputs (Feb 2026)
- `set_property('latched_lines', [...])` in connection table opts in specific DO channels
- Worker reads `latched_lines` from h5 `device_properties` per shot via `_ensure_str()`
- Pre-latch: `_ensure_manual_DO_task()` + `program_manual(latch_values)` before `stop_tasks()`
- Restore: three-layer merge (initial → cached_final → initial for latched) in both `post_experiment` and `transition_to_manual`
- `_ensure_manual_DO_task()` creates DO-only task (avoids AO glitch) when tasks cleared by `post_experiment`

## RasteringDevice / Rastering GUI (Mar 2026)
- GUI codebase: `GUIs/rastering/`, BLACS device: `userlib/user_devices/RasteringDevice/`
- GUI has its own CLAUDE.md at `GUIs/rastering/CLAUDE.md` with key file descriptions
- **Motor blocking**: `KCube.move_to()` spin-waits on `_task_complete` callback (~50ms poll). Motor is physically settled when `move_to()` returns.
- **Raster modes**: continuous (GUI auto-chains via `command_done_signal` → `_enqueue_next_raster_point`) and step (BLACS sends `move_to_next` per shot via REQ-REP)
- **Monitor values**: Tab shares `_pubsub_monitor_cache` dict with worker via `init_kwargs`. Worker snapshots `dict(cache)` for initial/final values — no REQ-REP CHECK_VALUE needed. **THIS IS THE CANONICAL FIX PATTERN** for "true measurement at shot boundaries" — reproduce for any RemoteControl subclass that needs it. LaserLockGUI does NOT yet have it (see below).
- **Uncalibrated guard**: `start_raster()` returns early if `self.calibration is None`
- **Race condition fix**: `_enqueue_next_raster_point()` holds `_state_lock` through both active check AND `next(iterator)` to prevent spurious enqueue after `stop_raster()`

## LaserLockGUI / HF_Locking (verified 2026-05-01)
- GUI codebase: `GUIs/HF_Locking/` (HF_Locking server). BLACS device: `userlib/user_devices/LaserLockDevice/`. Tab class: `LaserLockTab` (inherits `RemoteControlTab` but **overrides `initialise_GUI`** wholesale).
- **Shared `parent_port` design**: `TiSa_1_Setpoint` and `TiSa_1_Value` both have `parent_port='4'`. LaserLockTab intentionally avoids the base RemoteControlTab's second `create_analog_outputs(AM_prop)` call (which would clobber `self._AO['4']` with a monitor AnalogOutput). Comment at `LaserLockDevice/blacs_tabs.py:62-64` explains.
- **Wavemeter readings are not persisted to shot files.** PUB-SUB `freq_display` only updates `self._monitor_labels[conn]` (a QLabel) and `_update_error_display`. Nothing writes it to HDF5. `front_panel.base_value` for LaserLockGUI rows is the **server's stored setpoint as of the last 5-s `check_remote_values` poll** — neither the labscript-commanded value nor the wavemeter measurement.
- **`monitor_values/{initial,final}` is broken for LaserLockGUI**: `check_all_remote_values()` queries REQ-REP `CHECK_VALUE`, which `HF_Locking/workers.py:559-562` answers from `SharedExperimentState.setpoint`. So initial == final almost always (verified: 538/549 entries in scan 0015 were exactly equal). **Fix: apply RasteringDevice's `_pubsub_monitor_cache` pattern.**
- HF_Locking server returns server-side setpoint for `CHECK_VALUE`, broadcasts `freq_display` (wavemeter) on PUB-SUB. `PROGRAM_VALUE` round-trip via DLL decimal-string format introduces ~10 MHz quantization between labscript intent and server-stored setpoint.
- **Authoritative scanned setpoint per shot**: `/devices/LaserLockGUI/remote_device_operation` (float64). `front_panel.base_value` and `monitor_values` are both setpoint-flavored but lag/quantize. Use `remote_device_operation` for analysis x-axis.
- Full layout reference: `docs/shot-h5-layout.md` (case study + verified citations).

## NI_DAQmx ZMQ Socket Resilience (Mar 2026)
- Acquisition worker REQ socket had no timeout — blocked indefinitely after idle
- Fix: `RCVTIMEO=1000ms` + `_send_data(parts, timeout_ms)` helper at all 4 send/recv sites
- `_send_data` catches `zmq.Again`, resets socket via `_reset_data_socket()`, returns False
- `read()` callback (DAQmx thread): wraps `_send_data` in try/except — must never raise
- `post_experiment`: 5s timeout (large payloads); all others 1s
- Caller must hold `self.tasklock`; `_send_data` does NOT acquire it
- **Reusable pattern**: any ZMQ REQ socket talking to a potentially-slow peer should use this timeout+reset pattern

## Reusable Patterns

### GUI↔BLACS Feature Sync
When adding a feature to a BLACS tab, ask: "does this also make sense standalone in the external GUI?" If yes, sync via ZMQ PROGRAM_VALUE. Template: `sync_keep_warm_to_gui` sends `{prefix}_keep_warm = 0/1`, GUI dispatches via `_handleRemoteCommand`, sets checkbox via `setChecked()`. Add param to `WRITABLE_PARAMS` in ZMQ server.

### Hysteresis Threshold Automation
Two-threshold trigger/reset pattern with a `_triggered` flag. Prevents oscillation at boundary:
- Trigger at threshold_low (e.g., 37°C), set `_triggered = True`
- Reset at threshold_high (e.g., 39°C), set `_triggered = False`
- Guard: `if value < low and not triggered` / `elif value >= high and triggered`
Used in both BLACS tab (`_warmup_triggered`) and BigSky GUI (`_warmupTriggered`).

### Compound Function Sync Hazard
When a compound function (e.g., `startLaser()`) modifies state tracked by another system, check for one-way sync breaks. Example: GUI's `startLaser` was unchecking `keepWarmCheckBox` without notifying BLACS → BLACS still thought keep-warm was active. Fix: don't modify shared state in compound functions, or publish the change back.
