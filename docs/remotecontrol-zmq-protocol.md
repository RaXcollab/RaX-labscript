# RemoteControl ZMQ Protocol — v1 Reference (DEPRECATED 2026-05-23)

> **STATUS**: **v1 is dead code after the v2 cutover lands**
> ([`remotecontrol-zmq-protocol-v2.md`](remotecontrol-zmq-protocol-v2.md) is
> the live protocol — shipped on topic branches awaiting coordinated
> merge per [`docs/zmq-v2-cutover-runbook.md`](zmq-v2-cutover-runbook.md)).
> v2 servers REFUSE v1 envelopes (Q4 hard sunset); the BLACS-side
> `RemoteCommunication` client emits v2-only. New device or external-tool
> code MUST use v2. This doc is preserved for archaeological context only
> — the wire-format examples below no longer match runtime behavior.

> **Scope (historical)**: how custom external-GUI BLACS devices (`LaserLockDevice`, `RasteringDevice`, `BigSkyHub`) talked to their paired Qt GUIs over ZMQ before the v2 cutover. The 5-file device structure, the REQ-REP / PUB-SUB protocol, and the snapshot pattern for shot-h5 `monitor_values`.

Auto-loaded by `.claude/rules/ref-remotecontrol-zmq.md` when editing under `userlib/user_devices/` or `GUIs/`. Cross-reference: `docs/external-guis-architecture.md` (three-GUI overview), `docs/blacs-state-machine.md` (BLACS-side lifecycle), `docs/shot-h5-layout.md` (where monitor snapshots land).

## Two RemoteControl trees — one is dead code

- **ACTIVE**: `userlib/user_devices/RemoteControl/` — the live runtime base. Subclassed by `LaserLockDevice`, `RasteringDevice`, `BigSkyHub`. ALL new RemoteControl devices inherit from this copy.
- **DEAD CODE**: `labscript-devices/labscript_devices/RemoteControl/` — `register_classes.py` is fully commented out, so BLACS does not load it. Kept as the **protocol-reference ancestor** (the README and standalone classes still document the JSON schema). **No class inheritance** between the two trees.
- **Never** `import labscript_devices.RemoteControl` for new code. Use `from user_devices.RemoteControl.labscript_devices import RemoteControl, RemoteAnalogOut, RemoteAnalogMonitor`. Worker class string is `"user_devices.RemoteControl.blacs_workers.RemoteControlWorker"`.
- See [[reference_two-remotecontrol-trees]] (auto-memory).

## 5-file device structure

Every RemoteControl-derived device lives in `userlib/user_devices/{DeviceName}/`:

| File | Purpose |
|---|---|
| `__init__.py` | Empty package marker |
| `labscript_devices.py` | Connection-table API; subclasses `RemoteControl` (the userlib base). Compile-time only — no hardware I/O |
| `blacs_tabs.py` | BLACS GUI tab; subclasses `RemoteControlTab` |
| `blacs_workers.py` | Worker process; subclasses `RemoteControlWorker` |
| `register_classes.py` | Registers `(device name) → BLACS_tab` with `labscript_utils.device_registry` |

## REQ-REP protocol (BLACS → GUI command channel)

Worker holds a `RemoteCommunication` REQ socket (LINGER=0, SND/RCV timeouts 1000 ms; 120 s when `wait_for_lock=True`). All requests / replies are JSON.

### Request schema

```json
{ "action": "HELLO" | "CHECK_VALUE" | "PROGRAM_VALUE",
  "connection": "<conn_name>",         // e.g. "TiSa_1_Setpoint", "YAG_1_voltage"
  "value": <number-or-null>,
  "wait_for_lock": <bool, optional> }
```

### Reply schema

```json
{ "status": "SUCCESS" | "ERROR" | "TIMEOUT",
  "value": <number-or-null>,           // for CHECK_VALUE replies
  "message": "<string, on ERROR>" }
```

### Actions

- **HELLO** — connection probe. GUI replies SUCCESS, optionally fires its `_blacsHelloReceived` signal so per-laser controllers know BLACS is up. Used at worker init.
- **CHECK_VALUE** — read a setpoint or monitored value back. Used by `check_remote_values` poll (every 5 s on userlib RemoteControl tabs, see `docs/blacs-state-machine.md`).
- **PROGRAM_VALUE** — write a setpoint. Optional `wait_for_lock=True` extends the REQ socket RCV timeout to 120 s and asks the GUI to block until convergence (HF_Locking: 5 consecutive in-tol samples, see [[reference_hf-lock-thresholds]]).

### Error tokens (string-matched by BLACS workers)

- `"unknown connection '<name>'"` — GUI doesn't recognize the connection name; BLACS worker logs as `logger.debug` and continues
- `"laser disconnected"` (BigSky) — controller is offline; BLACS worker logs `logger.warning`
- `"rejected: <reason>"` — hardware refused the command (out-of-range, interlock); BLACS worker propagates as device error

### REQ socket resilience

REQ sockets enforce strict send-recv alternation. On `zmq.Again` timeout, `_reset_socket()` closes and re-creates the socket (LINGER=0 ensures clean close). Always called between `stop_task()` and `start_task()` (thread-safe window). **Never share a REQ socket between threads without a lock** — interleaved send/recv triggers unrecoverable EFSM. See `docs/blacs-device-patterns.md` "ZMQ REQ Socket Resilience".

### Mock mode

If `mock=True` in the connection-table properties, `RemoteCommunication` returns randomized dummy values without opening a socket. Useful for offline testing.

## PUB-SUB protocol (GUI → BLACS broadcast channel)

GUI is the PUB; BLACS tab + worker both subscribe.

### Topic schema

`"{connection_name}_{param}_monitor"` for monitors, `"heartbeat"` for liveness.

Example topics published by `LaserLockGUI`: `TiSa_1_Value_monitor`, `Vexlum_Value_monitor` (if implemented), `heartbeat`. By `BigSkyZmqServer`: `YAG_1_temperature_monitor`, `YAG_1_voltage_monitor`, `YAG_1_lamps_monitor`, etc., plus `heartbeat`.

### Payload format

`"{topic} {value}"` — space-separated, single ZMQ frame, value as `"%d"` for integer params and `"%.1f"` / `"%.3f"` / `"%.9f"` for floats. The receiving side parses by splitting on the last space.

### Cadence

- HF_Locking: 100 ms (10 Hz) per topic.
- Rastering: ~4 Hz aggregate (every cycle), `heartbeat` every 4th cycle (~1 Hz).
- BigSky hub: 250 ms loop, broadcasts every monitor topic each cycle (~4 Hz per laser), `heartbeat` every 4th cycle (~1 Hz).

### Two-thread bridge inside the BLACS tab

- **Heartbeat subscriber**: daemon thread polls SUB socket, emits `pyqtSignal` on connect/disconnect → bridge to GUI thread updates badges / icons.
- **Data subscriber**: daemon thread receives monitor values. `_on_monitor_value_received` does two things:
  1. Updates `_pubsub_monitor_cache` dict (tab-side cache).
  2. **Re-posts** the value into a BLACS-internal `Event` broker (`{device}_pubsub_monitor`, role `post`) so the worker subprocess can drain it.
- `_PubSubSignalBridge` is the QObject holding the signals. Never call widget methods from daemon threads directly — always go through the bridge.

### Worker-side drain thread

`RemoteControlWorker._pubsub_drain_loop` runs as a daemon thread inside the worker subprocess, reading the internal Event's `sub` socket directly (bypasses the identifier filter) into `self._pubsub_cache`. This is how the worker subprocess has access to live monitor values without needing its own PUB-SUB socket back to the GUI.

## Shot-h5 snapshot pattern (the "true measurement" record)

In `transition_to_buffered` (after programming the requested setpoints):

```python
self._save_monitor_values_to_hdf5(
    h5_file, 'initial_monitor_values', dict(self._pubsub_cache)
)
```

In `post_experiment`:

```python
self._save_monitor_values_to_hdf5(
    h5_file, 'final_monitor_values', dict(self._pubsub_cache)
)
```

Both write to `/data/{device}/monitor_values/{initial,final}_monitor_values` as compound datasets with one column per monitor connection, `dtype=float64` (was `float32` before 2026-04-29 — ~40 MHz ULP at WS-scale THz, unreliable; precision warning in `docs/shot-h5-layout.md`).

**Authoritative scan x-axis** = `/devices/{dev}/remote_device_operation['{ch}'][0]` (the actual labscript intent for that shot), NOT `monitor_values`. The monitor snapshot is the **measured readback**, not the setpoint. For setpoint-vs-readback drift analysis, both are needed.

**Wavemeter readings are PUB-SUB only and not persisted** — for HF_Locking the wavemeter value lives in `monitor_values` via the worker's drain snapshot, but no separate `wavemeter_*` dataset exists. The setpoint at `remote_device_operation` is what to plot for closed-cell scans (see [[reference_hf-lock-thresholds]] + `.claude/rules/analysis.md` "Authoritative Scan X-Axis").

## ZMQ contract symmetry rule

Changing any connection name or PUB-SUB topic requires updating BOTH:

1. The external GUI's ZMQ server (REP handlers + PUB topic strings).
2. The paired BLACS device under `userlib/user_devices/{Device}/`.

Mismatches show as `"unknown connection"` errors in BLACS.log and silent missing-monitor-values in shot h5 (PUB topic the BLACS subscriber doesn't recognize is silently dropped).

## Per-device poll cadence

| Device | `check_remote_values` poll | Notes |
|---|---|---|
| Base (`device_base_class.py:67`) | 30 s | Stock default; overridden by RemoteControlTab |
| All userlib RemoteControl tabs | **5 s** | `blacs_tabs.py:325` |
| During `wait_for_lock` | **500 ms** | `blacs_tabs.py:382`; back to 5 s after lock cycle |
| BigSky temp poll (per-laser) | 60 s | `tempPollTimer` QTimer in `SingleLaserController` |

## Three concrete implementations

- **HF_Locking** (`GUIs/HF_Locking/`, BLACS `LaserLockDevice`, ports 3796/3797) — wavemeter + laser lock; per-laser groupbox UI; `LaserLockTab` overrides `initialise_GUI` wholesale; outputs-only AO objects (monitors share parent_port).
- **Rastering** (`GUIs/rastering/`, BLACS `RasteringDevice`, ports 55535/55536) — motor stages; `transition_to_buffered` calls `move_to_next` with `wait_for_lock=True` BEFORE programming if `raster_mode` is on; PUB-SUB STATUS_TOPICS for raster progress.
- **BigSkyControl** (`GUIs/BigSkyControl/`, BLACS `BigSkyHub`, ports 55540/55541) — Nd:YAG lasers; split across `BigSkyControllerAmbitious.py` (per-laser widget) + `HugeSkyController.pyw` (hub + `BigSkyZmqServer`); 10 writable params per laser including `keep_warm`. See [[reference_bigsky-controller-split]].

## See also

- `docs/external-guis-architecture.md` — per-GUI architecture, Qt threading, file inventories.
- `docs/blacs-state-machine.md` — BLACS-side lifecycle; how `check_remote_values` fits the state machine.
- `docs/blacs-device-patterns.md` — patterns library incl. saved-state resilience, REQ socket resilience, ZMQ thread safety.
- `docs/shot-h5-layout.md` — exact dataset paths and dtypes for `monitor_values`.
