# Rastering GUI — BLACS Integration

**Date:** 2026-02-21
**Author:** Claude Opus 4.6 + Lab Member
**Repos:** `RaX-labscript` (labscript-suite) + rastering GUI (`GUIs/rastering`)

---

## What We Did

Integrated the rastering GUI (Thorlabs KCube motor control for laser ablation) into BLACS so that:

1. **Manual motor positioning** from BLACS — X/Y spinboxes in the BLACS tab
2. **Per-shot raster stepping** — BLACS auto-arms the raster (step mode) and advances it one point every N shots during `transition_to_buffered` (N = "Shots per step" spinbox, default 1; updated 2026-07-31)
3. **Live status monitoring** — PUB-SUB broadcasts position, raster mode, calibration status, and progress to BLACS with colored indicators
4. **Position recording** — X/Y motor position captured to HDF5 each shot for analysis

## Architecture

```
Rastering GUI (localhost)          BLACS (RasteringDevice tab)
┌─────────────────────┐           ┌──────────────────────────┐
│  ZMQ REP :55535     │◄──REQ────►│  RasteringWorker         │
│  (HELLO, PROGRAM,   │           │  (move_to_next, CHECK)   │
│   CHECK_VALUE)      │           │                          │
│                     │           │                          │
│  ZMQ PUB :55536     │───SUB────►│  RasteringTab            │
│  (heartbeat, pos,   │           │  (position monitors,     │
│   mode, cal, prog)  │           │   colored indicators)    │
└─────────────────────┘           └──────────────────────────┘
```

## Files Changed

### Rastering GUI (`GUIs/rastering/`)

| File | Change |
|------|--------|
| `config.py` | Added `pub_bind: str = "tcp://*:55536"` to NetworkConfig |
| `raster_controller.py` | Added HELLO handler, PUB-SUB publisher in `_zmq_loop`, raster step counter tracking |
| `main_rastering.py` | Pass `pub_bind` to `start_zmq_server()` |

### Labscript-suite (`labscript-suite/`)

| File | Change |
|------|--------|
| `userlib/user_devices/RasteringDevice/__init__.py` | Empty (new) |
| `userlib/user_devices/RasteringDevice/labscript_devices.py` | `RasteringDevice(RemoteControl)` subclass (new) |
| `userlib/user_devices/RasteringDevice/register_classes.py` | BLACS registration (new) |
| `userlib/user_devices/RasteringDevice/blacs_workers.py` | `RasteringWorker` with `move_to_next` logic (new) |
| `userlib/user_devices/RasteringDevice/blacs_tabs.py` | `RasteringTab` with colored indicators + raster checkbox (new) |
| `userlib/labscriptlib/Main_Experiment/connection_table.py` | Added RasteringGUI device + X/Y outputs/monitors |

## Connection Table Entry

```python
from user_devices.RasteringDevice.labscript_devices import RasteringDevice

RasteringDevice(name='RasteringGUI', host="127.0.0.1", reqrep_port=55535, pubsub_port=55536, mock=False)

# Writable position controls (manual mode)
RemoteAnalogOut(name='Raster_X', parent_device=RasteringGUI,
    connection="laser_raster_x_coord", units="mm", limits=(0, 25.0), decimals=4, step_size=0.001)
RemoteAnalogOut(name='Raster_Y', parent_device=RasteringGUI,
    connection="laser_raster_y_coord", units="mm", limits=(0, 25.0), decimals=4, step_size=0.001)

# Live position monitors (PUB-SUB)
RemoteAnalogMonitor(name='Raster_X_Monitor', parent_device=RasteringGUI,
    connection="laser_raster_x_coord_monitor", units="mm", limits=(0, 25.0), decimals=4)
RemoteAnalogMonitor(name='Raster_Y_Monitor', parent_device=RasteringGUI,
    connection="laser_raster_y_coord_monitor", units="mm", limits=(0, 25.0), decimals=4)
```

## How to Use

### Manual Positioning
1. Start rastering GUI, then start BLACS
2. Use X/Y spinboxes in the RasteringGUI tab to move motors
3. Position updates live via PUB-SUB (~4 Hz)

### Per-Shot Rastering (updated 2026-07-31)
1. In the rastering GUI: configure a raster path (calibration required). Arming from the GUI is optional — BLACS auto-arms.
2. In BLACS: check the **"Raster Mode"** checkbox and set **"Shots per step"** (N shots at each raster position; default 1). Ticking the box arms the GUI **right then** (`arm_raster` + `shots_per_step`) — the GUI's mode indicator turns green immediately; unticking sends `disarm_raster`.
3. Queue shots — on the first shot of each group of N, `transition_to_buffered` sends `arm_raster` (only if not already armed) then `move_to_next`.
4. The rastering GUI moves to the next point, waits for the motor to settle, replies.
5. BLACS captures X/Y position to HDF5, then proceeds with the shot.
6. When the raster path is exhausted, the GUI wraps natively (2026-08-03): a BLACS-driven `move_to_next` past the last point rewinds the cursor to point 0, so queued shots repeat the armed pattern indefinitely and BLACS never sees `finished`. The armed pattern is **immutable** until a fresh arm — mid-queue spec edits do nothing. For exactly one pass, queue `path_len × shots_per_step` shots from a fresh arm. Since 2026-08-04 the operator's local Step wraps identically (the zmq-vs-ui split is gone); Stop/disarm are the only ways a non-empty armed raster ends. BLACS retains a re-arm-on-`finished` fallback for older GUI builds (that path rebuilds from live settings). The GUI progress display counts monotonically, so it may read e.g. 13/10 on pass 2.

Details of the stepping state (worker-side):
- Checkbox + spinbox state is persisted across BLACS restarts and forwarded to the worker via workerargs (restore runs before `initialise_workers`), so a restored-checked box actually steps — pre-2026-07-31 it silently didn't.
- The group counter persists across queue end (no `transition_to_manual` between queued shots); pausing/resuming a queue does not restart the group count. Changing either control resets the counter.
- **Eager sync (`_sync_raster_mode_to_gui`, blacs_workers.py:88).** Both controls push to the GUI the moment they change, and again on every (re)connect — before this, nothing reached the GUI until the first shot, so ticking the checkbox looked like it did nothing. Rules: arming is skipped when we already believe the GUI is armed (re-arming would restart the path from point 1, so an N change on a live raster only re-sends N); `disarm_raster` is sent only on a checked→unchecked transition or when we believe the GUI is armed, so a spinbox jiggle with the box unchecked touches nothing.
- **The eager path never raises.** Toggling the checkbox with the GUI closed logs one line and stops (a red BLACS tab from a checkbox click is unacceptable), and every failure — typed server error or dead transport — becomes a warning. On a failed arm the armed flag stays False, so `_advance_raster`'s lazy arm is the backstop and the operator still finds out at the first shot. That per-shot path keeps its loud-raise semantics: a failed arm or step **must** fail the shot.
- **Front-panel pushes are courtesy writes (2026-08-04).** `RasteringWorker.program_manual` warns and continues on a refused channel write instead of raising: BLACS re-asserts the full front panel on every queue abort (and once at tab startup), and a refused edge coordinate there must not red-error the tab — a sticky tab error silently blocks `transition_to_buffered` for **all** later shots until the operator dismisses it. Shot programming in `transition_to_buffered` stays strict.
- Syncing N is best-effort everywhere, including in the lazy-arm path: the GUI only *displays* N, BLACS owns the stepping decision, so a failed `shots_per_step` never fails a shot.
- A failed step does not advance the counter, so a retried shot still performs a *step* — it never fires at the previous position. The point whose move failed is skipped, however: the GUI consumes the path point before enqueuing the move, so the retry steps to the *next* point and the failed point is never shot.
- The shot counter advances at `transition_to_buffered`, so a shot that aborts mid-run still counted — that raster position ends up with fewer than N shots. Analysis should group shots by the X/Y position recorded in the h5, not assume exactly N shots per position.

Raster control messages (all `PROGRAM_VALUE`, v2 envelope):

| Connection | Value | Sent from | Reply |
|---|---|---|---|
| `arm_raster` | `0` (step mode) | eager sync on tick/reconnect; lazy arm in `_advance_raster` | SUCCESS carries `mode`; typed errors `no_raster_configured`, `not_calibrated` |
| `shots_per_step` | N ≥ 1 | after every successful arm, and on an N change while armed | SUCCESS; `invalid_value` on garbage. Display-only on the GUI — failures are warnings |
| `disarm_raster` | `1` | eager sync on untick | SUCCESS `{"disarmed": bool}`, idempotent when inactive; `raster_in_continuous_mode` means the GUI operator owns that raster — warn, don't fight it |
| `move_to_next` | `1` | first shot of each group of N | SUCCESS, or SUCCESS + `finished: true` at path end |

### Status Indicators
- **Raster Mode**: Green = "Step" (ready for BLACS), Yellow = "Continuous", Gray = "Idle"
- **Calibration**: Green = calibrated, Red = uncalibrated
- **Progress**: Shows "Step N/M" during raster

## PUB-SUB Message Format

Messages follow the RemoteControl convention: `"{topic} {value}"` (space-separated string).

| Topic | Example | Rate |
|-------|---------|------|
| `heartbeat` | `"heartbeat"` | ~1 Hz |
| `laser_raster_x_coord_monitor` | `"laser_raster_x_coord_monitor 12.345"` | ~4 Hz |
| `laser_raster_y_coord_monitor` | `"laser_raster_y_coord_monitor 6.789"` | ~4 Hz |
| `raster_mode` | `"raster_mode step"` | ~1 Hz |
| `calibration_status` | `"calibration_status calibrated"` | ~1 Hz |
| `raster_progress` | `"raster_progress 5/20"` | ~1 Hz |

## HDF5 Data Location

After each shot, X/Y position is saved to:
```
data/RasteringGUI/monitor_values/initial_monitor_values
data/RasteringGUI/monitor_values/final_monitor_values
```

Each dataset contains columns: `laser_raster_x_coord`, `laser_raster_y_coord`, `laser_raster_x_coord_monitor`, `laser_raster_y_coord_monitor`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| BLACS tab shows red "CONNECTION FAILED" | Start the rastering GUI before BLACS, or click reconnect |
| "raster_arm error: no_raster_configured / not_calibrated" | Configure a raster path (and calibrate) in the rastering GUI — BLACS auto-arms but cannot invent a path |
| "Raster move_to_next error: raster_not_active" | Should not occur since auto-arm (2026-07-31); if it does, the GUI likely restarted mid-queue — toggle Raster Mode to re-arm |
| "Raster re-armed but immediately reported 'finished'" | Should not occur (loop-bound guard — an empty path fails the *arm* with `no_raster_configured` instead). If seen, the GUI reported finished right after a successful arm: check the raster state in the rastering GUI |
| Status indicators stay gray | Check that PUB-SUB port 55536 matches in both config.py and connection table |
| Motor move timeout | Large moves may exceed the 5s default timeout; position small moves from BLACS, large moves from rastering GUI |

## Future Enhancements

- Save raster path geometry and calibration to HDF5 for each shot
- `arm_raster` and `move_to_next` as connection table channels (needs custom `program_manual` to skip in manual mode)
- Camera integration in BLACS tab (if latency is acceptable)
