# Rastering GUI — BLACS Integration

**Date:** 2026-02-21
**Author:** Claude Opus 4.6 + Lab Member
**Repos:** `RaX-labscript` (labscript-suite) + rastering GUI (`Desktop/GUIs/rastering`)

---

## What We Did

Integrated the rastering GUI (Thorlabs KCube motor control for laser ablation) into BLACS so that:

1. **Manual motor positioning** from BLACS — X/Y spinboxes in the BLACS tab
2. **Per-shot raster stepping** — BLACS automatically advances the raster one point per shot during `transition_to_buffered`
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

### Rastering GUI (`Desktop/GUIs/rastering/`)

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

### Per-Shot Rastering
1. In the rastering GUI: configure a raster path, click "Start Raster" in **step mode**
2. In BLACS: check the **"Raster Mode"** checkbox in the RasteringGUI tab
3. Queue shots — each shot's `transition_to_buffered` sends `move_to_next` to the rastering GUI
4. The rastering GUI moves to the next point, waits for the motor to settle, replies
5. BLACS captures X/Y position to HDF5, then proceeds with the shot
6. When the raster path is exhausted, the shot queue stops with a "Raster sequence complete" error

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
| "Raster move_to_next error: raster_not_active" | Arm the raster in the rastering GUI (step mode) before starting shots |
| "Raster sequence complete" stops queue | Re-arm the raster with a new path in the rastering GUI |
| Status indicators stay gray | Check that PUB-SUB port 55536 matches in both config.py and connection table |
| Motor move timeout | Large moves may exceed the 5s default timeout; position small moves from BLACS, large moves from rastering GUI |

## Future Enhancements

- Save raster path geometry and calibration to HDF5 for each shot
- `arm_raster` and `move_to_next` as connection table channels (needs custom `program_manual` to skip in manual mode)
- Raster state persistence across BLACS restarts (save checkbox state)
- Camera integration in BLACS tab (if latency is acceptable)
