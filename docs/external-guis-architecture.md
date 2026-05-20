# External GUIs Architecture

> **Scope**: per-GUI internals for the three registered external GUI codebases (`HF_Locking`, `rastering`, `BigSkyControl`). Shared patterns, Qt threading, file inventories, common pitfalls.

Auto-loaded by `.claude/rules/ref-external-guis.md` when editing under `userlib/user_devices/` or `GUIs/`. Cross-reference: `docs/remotecontrol-zmq-protocol.md` (protocol spec), `docs/blacs-state-machine.md` (BLACS-side lifecycle).

## Common pattern

Every external GUI:

1. Hosts a ZMQ REP server (BLACS sends commands here) + a ZMQ PUB server (broadcasts monitors).
2. Pairs with a BLACS device under `userlib/user_devices/` that subscribes to PUB topics and sends REQ-REP requests.
3. Lives in its own conda environment (varies per GUI).
4. Has its own `.claude/agents/` domain agent.
5. May ship its own GUI-local `CLAUDE.md` for operator + agent context.

Three concrete implementations diverge in threading model — see `docs/remotecontrol-zmq-protocol.md` "Three concrete implementations" + Thread 2.2 of the brainstorm for a future-unification opportunity.

---

## HF_Locking

### Hardware

HighFinesse WS7-30 wavemeter (8 channels via fiber switcher) accessed via `wlmData.dll` (ctypes). Locks lasers to per-channel setpoints via the WLM's PID; BLACS programs setpoints through this GUI.

### ZMQ ports

- **REP 3796** — `ZMQRepWorker(QThread)`, 50 ms poller. Actions: `HELLO`, `CHECK_VALUE` (returns SharedExperimentState setpoint — NOT GUI text — for the requested channel), `PROGRAM_VALUE` (emits `request_setpoint_write` cross-thread). Optional `wait_for_lock` extends RCV timeout to 120 s and blocks until convergence.
- **PUB 3797** — `ZMQPubWorker(QThread)`, 10 Hz. Broadcasts `"heartbeat"` then `"{port} {freq_display or 0.0}"` ×8 channels per cycle.

### Lock acquisition spec (canonical)

- `LOCK_TIMEOUT_S = 60 s` (`workers.py:21`)
- `LOCK_CONSECUTIVE = 5` (`workers.py:22`) — five consecutive fresh in-tolerance samples required
- `LOCK_TOLERANCE = 5e-6 THz = 5 MHz` (`workers.py:20`)
- Inner poll 25 ms (40 Hz) — matches WS7 aggregate update rate across 8 channels
- Skips `wlmConst.InfNothingChanged` (-7) sentinel — those are stale cache hits, not fresh measurements

See [[reference_hf-lock-thresholds]] and `docs/hf-locking-rates.md`.

### Qt structure

- `wlm_link` (DLL handle) lives in main thread; created at startup, used only at startup / shutdown.
- **`WavemeterWorker(QObject)`** moved to `thread_wlm` (QThread) — owns all runtime DLL I/O. Fast poll **`PreciseTimer` @20 ms**: rule-compliant because it's on a worker QThread (PreciseTimer on GUI thread freezes Windows; see [[feedback_qt-precisetimer-gui-thread-windows]]).
- GUI-thread timers `_gui_timer_fast` / `_gui_timer_slow` are explicitly `CoarseTimer`.
- **PULL model**: GUI timers read `SharedExperimentState[QMutex]` snapshots (33 ms fast / 1 s slow). Worker→GUI signals only for write-handler feedback.
- Re-entrancy guards `_busy_fast` / `_busy_gui_fast` log `[PERF]` on overload.
- Win32: `SetPriorityClass=ABOVE_NORMAL` (see [[feedback_above-normal-priority-default]]) + EcoQoS opt-out (see [[feedback_win11-dual-throttling]]) — both rule-compliant.
- Multi-monitor: `TARGET_SCREEN=r"\\.\DISPLAY5"` matched by `QScreen.name()` with primary fallback.

### Setpoint race fix (`display.py`)

`ChannelControl` uses a `textEdited`-driven `_setpoint_dirty` flag (not focus/pending-guard). `update_slow` setText guarded by `not hasFocus() and not _setpoint_dirty and now > pending_until`. Cycle-shift pyqtgraph plot for wrap-around: store raw elapsed in deque, render as `t % sweep` with old-cycle shift `-=sweep` for `clipToView` + visible-window Y-autoscale.

### File inventory

| File | Role |
|---|---|
| `main_wlm.py` | `ExperimentController(QMainWindow)`, `_RestoreDialog`, startup config diff + restore, shutdown saves config |
| `workers.py` | `SharedExperimentState`, `WavemeterWorker`, `ZMQRepWorker`, `ZMQPubWorker` |
| `display.py` | `ChannelControl`, `GlobalControl`, `ElapsedAxisItem`, plot helpers |
| `wlm_utils.py` | DLL wrapper functions (`get_pid_setting`, `set_pid_course_num`, etc.) |
| `config.py` | `read_live_state`, `save_settings`, `load_settings`, `compare`, `restore_settings`, `backup_wlm_config`; PID_DOUBLE/INT, LC_DOUBLE/INT registries |
| `wlmConst.py` / `wlmData.py` | DLL constants and function signatures (read-only) |
| `diagnostics.py` | Instrumentation hooks; `ENABLED=False` in production |

### Domain agent

`pid-persistence.md` (opus). Original task spec is 3 months old (2026-02-25) — verify status against current code before treating as live spec.

### Paired BLACS device

`userlib/user_devices/LaserLockDevice/`. Marker subclass of `RemoteControl`. `LaserLockTab` overrides `initialise_GUI` wholesale (per-laser groupbox UI, `_LOCK_THRESHOLD_MHZ=100`). Creates outputs-only AO objects (monitor children share `parent_port`; second `create_analog_outputs` would clobber `_AO`). `_fetch_initial_values` shows saved-vs-remote mismatch QMessageBox (handles GUI-restart-zeros-setpoints case).

---

## Rastering

### Hardware

Thorlabs KCube DCServo Z912 motors (X serial 27270522, Y serial 27270471) via Kinesis pythonnet. IDS uEye camera (pyueye). Steers an ablation laser spot.

### ZMQ ports

- **REP 55535** — `_zmq_loop` daemon thread, RCVTIMEO 250 ms. Actions: `HELLO`, `CHECK_VALUE` (`laser_raster_x/y_coord[_monitor]` → cached target else live motor), `PROGRAM_VALUE` (`laser_raster_x_coord` / `y_coord` → `request_move_x/y(wait=True)`; `arm_raster` truthy = continuous; `move_to_next` → one `raster_step`, replies FINISHED on StopIteration).
- **PUB 55536** — ~4 Hz aggregate. Per cycle: `laser_raster_x/y_coord_monitor`. Every 4th cycle: `heartbeat`, `raster_mode` (idle / continuous / step), `calibration_status`, `raster_progress` `{step}/{total}`.

### Qt / threading

- **Single-owner motor I/O thread** `_motor_worker_loop` — only place motor DLL is touched. Commands via `queue.PriorityQueue` keyed `(priority, next(itertools.count()), cmd)` — **monotonic tiebreaker**, see [[reference_priorityqueue-monotonic-tiebreaker]]. Priorities: STOP=0, READ_POS / GET_BACKLASH=50, normal=100, telemetry=200.
- `_wait_reply`: GUI-thread callers drive `processEvents(ExcludeUserInputEvents, 30 ms)` to avoid freeze during long motor waits. Non-GUI callers use blocking `get`.
- Raster chaining: `command_done_signal` → `_on_command_done` (for `raster_step` tag only) → continuous mode re-enqueues via `_enqueue_next_raster_point`. Lock held through active-check + `next(iter)` + enqueue (full critical section, guards `QTimer.singleShot` race).
- Calibration: `AffineCalibration` (3+ points, collinearity guard); bundled JSON (matrix + offset + user_home + backlash + camera_settings); `last_calibration_state.json` breadcrumb.

### MotorCommand logging discipline

`_LOGGABLE_SUCCESS_TAGS` / `_LOGGABLE_START_TAGS` + `_format_*` branches: a new `MotorCommand` tag MUST be added to BOTH whitelists and have a `_format_*` branch, or the motor moves but logs NOTHING and reads as broken. Has bitten twice. See [[reference_motorcommand-tag-logging-whitelist]].

### Spinbox commits

Backlash commits via explicit "Set" QPushButton, NOT `editingFinished` — follows the rule [[feedback_qt-precisetimer-gui-thread-windows]] (`editingFinished` double-fires). Spinbox seeding uses `blockSignals`. `_apply_loaded_backlash_widgets` deliberately avoids priority-50 GET after priority-100 SET (priority-inversion fix; Bugs A–E test pin).

### Camera

`UEyeCamera` (MONO8, strict pclk → fps → exposure ordering, AOI 4-px aligned). `UEyeCameraThread(QThread)` with unified mutex-protected `_pending` dict. Transient SDK codes 122 / 178 throttled. INI loader/saver with custom `[Display]` section. `_slider_to_phys` / `_phys_to_slider` single-source mapping; `_bind_param_controls` wires display-sync + camera-commit together.

### File inventory

| File | Role |
|---|---|
| `raster_controller.py` | `SystemController`, `AffineCalibration`, `CalibrationSession`, `CommandType`/`MotorCommand`/`MotorResult`, `_zmq_loop`, factory |
| `ui.py` | `RasterMainWindow` — pyqtgraph ImageItem, click → calibrate / hull, jog screen→motor mapping. NO ZMQ / DLL access |
| `hardware.py` | `KCube`, `Motor`, `SimulatedMotor`, Kinesis loading, move timeouts |
| `camera.py` | `UEyeCamera`, `UEyeCameraThread` |
| `camera_settings_dock.py` | `CameraSettingsDock(QDockWidget)` |
| `raster_paths.py` | Pure path generators: serpentine / spiral / hull iterators, `RasterSpec`. No Qt or DLL |
| `config.py` | Frozen dataclasses `APP_CONFIG` |
| `main_rastering.py` | `build_controller`, auto-load last calibration |
| `tests/test_command_queue.py` | Bugs A–E test pins |
| `tests/test_exposure_slider_camera.py` | Slider→camera commit test pin |

### Domain agent

`ablation-tech.md` (opus). Recently fixed broken `amo-lab-engineer` references (2026-05-19 refactor).

### Conda env

**`rastering`** (NOT `labscript`). Separate to isolate pythonnet / pyueye dependencies.

### Paired BLACS device

`userlib/user_devices/RasteringDevice/`. `RasteringWorker.transition_to_buffered`: if `raster_mode` is on (tab checkbox → `update_raster_mode`), sends `move_to_next` with `wait_for_lock=True` BEFORE programming setpoints; raises on `status=="FINISHED"` (path exhausted) or `ERROR`. Otherwise just programs setpoints, snapshots `_pubsub_cache`. `RasteringTab` overrides `_subscriber_loop` to also subscribe `STATUS_TOPICS` (raster_mode / calibration_status / raster_progress) via `_StatusSignalBridge` → colored `StatusIndicator` badges.

---

## BigSkyControl

### Hardware

Quantel Big Sky Nd:YAG pulsed lasers (×2 on this PC) via RS-232. 9600 baud, 1 s timeout, 140-byte reads, `>cmd\n` requests, `\r\n` precedes responses.

### File split

**Two files** — read both, never just one:

- `BigSkyControllerAmbitious.py` (1072 LOC) — contains ONLY `SingleLaserController(QWidget, Ui_Widget)`. Per-laser widget; serial I/O via `_sendCommand()`; all `_handleRemoteCommand` dispatch; all thread-safe `get*()` getters; `executeRemoteCommand` slot; `_blacsHelloReceived` and `connectionStatusChanged` signals. Loads `GuiBigSkyWidget.ui` via `uic.loadUiType`.
- `HugeSkyController.pyw` (479 LOC) — multi-laser hub. Contains `BigSkyZmqServer` (the actual ZMQ REP 55540 / PUB 55541 server), `BigSkyHub(QMainWindow)`, `MyTableWidget` (tab container), `HomeTab` (COM-port scanner + label editor).

See [[reference_bigsky-controller-split]].

### ZMQ ports + params

- **REP 55540** — `BigSkyZmqServer` daemon thread, 250 ms RCVTIMEO. Actions: `HELLO`, `CHECK_VALUE`, `PROGRAM_VALUE`.
- **PUB 55541** — same daemon thread, broadcasts every cycle (~4 Hz), `heartbeat` every 4th cycle.
- **`WRITABLE_PARAMS`** (10 — note `keep_warm`): `voltage, shutter, lamps, qswitch, lamp_mode, qswitch_mode, warmup, start_lasing, stop, keep_warm`.
- **`MONITOR_PARAMS`** (5, PUB-SUB suffixes): `temperature, voltage, lamps, shutter, qswitch`.
- **`CHECKABLE_PARAMS`** (7): `MONITOR_PARAMS ∪ {lamp_mode, qswitch_mode}`.

### Threading bridge

`PROGRAM_VALUE` arrives on the ZMQ daemon thread → creates a `concurrent.futures.Future` → emits `pyqtSignal(connection_name, ctrl, future)` queued to Qt main thread → `_handleRemoteCommand` runs serial I/O on main thread → writes `{status, message, value}` to the future. ZMQ thread blocks `future.result(timeout=10.0)` and returns the reply.

Why this matters: serial I/O must NOT happen on the ZMQ daemon thread (would mix Qt signals with blocking serial). `Future`-based bridge gives explicit timeout + rejection-path propagation.

### Serial gateway pattern

ALL serial I/O routes through `_sendCommand(cmd_bytes)` in `SingleLaserController` → returns response str or None. Catches `SerialException`, `OSError`, `UnicodeDecodeError`. After 3 consecutive empty / decode errors → `_handleDisconnect`. Raw `self.ser.*` access exists only in `_sendCommand`, `_attemptReconnect`, `safeExit`. **Follows the serial-disconnect-gateway pattern; standard for all serial RemoteControl GUIs.**

### State machine

Integer flags `activeStatus` / `shutterStatus` / `qSwitchStatus` under `_stateLock` (`threading.Lock`). `updateAllStatusIndicators` is the central enable/disable + color authority: shutter requires lamps; qswitch requires lamps + shutter; mode radios standby-only; singlePulse requires `qswitch_mode==0`.

### Compound sequences

- **`startWarmup`**: `>s` → `setFlashLampInternal` (verify mode == 0, abort if not) → `>a` (internal trigger, shutter closed).
- **`startLaser`** ("Arm External"): `>s` → `setFlashLampExternal` (verify mode == 1) → `>a` → `>r1` → `>pq`. Each step checks `_sendCommand` return value and `serialConnected`.
- **`stopLaser`**: `>s`, resets flags.

`_setLampMode` parses and verifies the controller-reported mode (`_TRAILING_INT_RE`), caches the **actual** value, returns `{status:ERROR, message:"rejected: ..."}` on serial/parse/verify-mismatch. **Setter Verify Gap** (known issue, not yet fixed): voltage / q-switch / shutter setters cache without verify, bounded by ~10 s `check_remote_values` resync.

### Hub-level state

No cross-laser interlocks. Each `SingleLaserController` is fully independent. Hub owns only the ZMQ server, tab container, and `_laserLaunchOrder` counter (counter never decrements; once `LASER_SN_TO_CONNECTION` is populated, counter becomes moot). `LASER_SN_TO_CONNECTION` populated in 2026-05-19 refactor with `{'151': 'YAG_1', '213': 'YAG_2'}`.

### Spinbox commits

`frequencyDoubleSpinBox` connects BOTH `valueChanged` and `editingFinished` to `setFrequency` — but `setFrequency` only caches `proposedFrequency`; actual hardware write is a separate `frequencyConfirmationButton.clicked` → `confirmFrequencySetting`. So `editingFinished` double-fire is mitigated by the explicit confirm-button pattern (no double hardware write).

### Conda env

**`guis`** (NOT `labscript`, NOT `rastering`).

### Domain agent

`bigsky-yag-laser-controller.md` (opus, blue). May have minor drift on `keep_warm` and method names — verify against code on contact (recently flagged in 2026-05-19 audit).

### Paired BLACS device

`userlib/user_devices/BigSkyHub/`. `BigSkyHub` auto-generates 9 writable + 5 monitor children per laser (`YAG_n_voltage`, `YAG_n_temperature`, etc.). `BigSkyWorker` enforces `COMMAND_ORDER` (stop → modes → voltage → lamps → shutter → qswitch → warmup), `_CMD_DELAY_S=0.2` between stop and mode changes, delta-track via `_last_sent_values`. Two-tier `_is_armed` flag + `_verify_armed_state` CHECK_VALUE. **`transition_to_manual` resets flags only** (no hardware — pause-safe). Keep-warm hysteresis 37 / 39 °C, `_evaluate_keep_warm`. `get/restore_save_data` persists checkboxes (remember-only, never fires lamps in restore).

---

## ZMQ contract symmetry (load-bearing)

Changing any connection name or PUB topic requires updating BOTH the GUI and the paired `userlib/user_devices/{Device}/`. Mismatches show as `"unknown connection"` REQ errors in BLACS.log and silent missing-monitor-values in shot h5 (PUB topic the BLACS subscriber doesn't recognize is silently dropped).

## See also

- `docs/remotecontrol-zmq-protocol.md` — protocol spec, error tokens, REQ socket resilience, shot-h5 snapshot pattern.
- `docs/blacs-state-machine.md` — BLACS lifecycle; how `check_remote_values` fits the state machine.
- `docs/yag-laser-physics.md` — Nd:YAG physics + trigger modes + serial command reference.
- `docs/hf-locking-rates.md` — full rate inventory for HF_Locking.
- `.claude/rules/devices.md` — Qt thread-safety + per-shot teardown invariants.
- GUI-local docs: `GUIs/BigSkyControl/CLAUDE.md`, GUI-local agents in `GUIs/*/.claude/agents/`.
