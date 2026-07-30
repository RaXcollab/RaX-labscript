# Main_Experiment — This Machine's Setup

> **Scope**: the active experimental setup on `RaX-Control` — connection-table topology, channel inventory, scope-trigger idiom, latched-lines convention, active vs legacy sequences, globals model. This doc is lab-machine-specific.

Auto-loaded by `.claude/rules/ref-main-experiment.md` when editing under `userlib/labscriptlib/Main_Experiment/`. Cross-reference: `docs/blacs-state-machine.md`, `docs/remotecontrol-zmq-protocol.md`, `docs/external-guis-architecture.md`, `docs/shot-h5-layout.md`.

## Active connection table

`userlib/labscriptlib/Main_Experiment/connection_table.py` — BLACS loads **only this file**. The other `connection_table_*.py` files are materially different backups (different COM ports, different `num_AI`, different device presence). **Do not edit a backup expecting it to take effect.**

### Pseudoclock topology

- **`PrawnBlaster(name='pb', com_port='COM4', num_pseudoclocks=2)`** — master clock, 10 MHz output, 20 ns resolution, 30000 instr/pseudoclock cap.
  - `pb.clocklines[0]` → **`ni_6361`** (Pseudoclock 0)
  - `pb.clocklines[1]` → **`ni_6535`** (Pseudoclock 1)

### NI hardware

| Device | Class | MAX_name | clock_terminal | Key kwargs |
|---|---|---|---|---|
| `ni_6361` | `NI_PXIe_6361` | PXI1Slot8 | `/PXI1Slot8/PFI1` | `acquisition_rate=100e3`, `stop_order=-1`, `AI_term='Diff'`, `num_AI=6`, `num_AO=2` |
| `ni_6535` | `NI_PXIe_6535` | PXI1Slot5 | `/PXI1Slot5/PFI4` | `stop_order=1` (digital-only) |
| `NI_SCOPE` | `NI_SCOPE` (custom user_device) | PXI1Slot2 | n/a (NI-5922 digitizer) | `vertical_range=[0.5,0.1]`, `coupling=['DC','DC']`, `min_sample_rate=1e6`, `min_num_pts=200_000`, `trigger_source='TRIG'`, `trigger_level=1.0`, `channels_to_save=[0,1]` |

### Analog channels on `ni_6361`

- **AnalogIn**: `daq_ai0` through `daq_ai5` (ai0–ai5), Diff terminal.
- **AnalogOut**: `daq_ao0` (ao0 — used for NI-5922 TRIG, ±2.5 V pulse), `daq_ao1` (ao1 — unused).

### Digital outs on `ni_6535` (port0)

- `LIF_shutter` = line0 — **the only registered latched line** on this PC, declared via `ni_6535.set_property('latched_lines', ['port0/line0'], location='device_properties')`. See [[reference_ni-daqmx-latched-lines-three-layer-restore]].
- `YAG1_line` = line1
- `YAG2_line` = line2
- `ENH_line` = line3 — currently also used as a "dummy DO pad" in `Open_cell.py` to satisfy NI-DAQmx's even-children-DO constraint (a real shutter pressed into duty as buffer padding).

### External-GUI devices (connection-table names)

| CT name | BLACS device | Hardware | Ports | Notes |
|---|---|---|---|---|
| `LaserLockGUI` | `LaserLockDevice` | HighFinesse WS7-30 wavemeter + laser lock | 3796 / 3797 | `host=127.0.0.1`, `mock=False`, `wait_for_lock=True`. Children: `Vexlum_Setpoint` (conn 3), `TiSa_1_Setpoint` (conn 1), `TiSa_2_Setpoint` (conn 6) — units THz, decimals 9. Monitor children: `TiSa_1_Value`, `TiSa_2_Value`. No Vexlum monitor child |
| `RasteringGUI` | `RasteringDevice` | Thorlabs Z912 ×2 + IDS uEye camera | 55535 / 55536 | Children: `Raster_X`/`Raster_Y` (conn `laser_raster_x_coord`/`_y_coord`, units mm, limits 0–25), `Raster_X_Monitor`/`Raster_Y_Monitor` |
| `BigSkyLasers` | `BigSkyHub(num_lasers=2, laser_prefix="YAG")` | Quantel Big Sky Nd:YAG ×2 | 55540 / 55541 | Auto-created children. Sequences reference `YAG_1_voltage`, `YAG_2_voltage` (set via `.constant(value)`). 10 writable params per laser including `keep_warm` |

## Sequences

All sequences live in `sequences/`. The CT is imported via `from labscriptlib.Main_Experiment.connection_table import connection_table; connection_table()`.

### Active sequences

| File | Purpose | Globals used |
|---|---|---|
| `Open_cell.py` | Open-cell absorption, 6 AI channels | `TISA_1, V_YAG1, V_YAG2, DOUBLE_YAG, tYAG_1, tYAG_2, tstart, tend` |
| `Closed_cell.py` | Closed-cell absorption, dual-TiSa, ENH pulse | adds `TISA_2, ENH_SHUTTER_OPEN, ENH_START, ENH_DURATION` |
| `Closed_cell_scan.py` | Frequency-scan variant; **`freq_ramp` is the scan global**. `latch_digital(LIF_shutter, LIF_SHUTTER_OPEN)` is ACTIVE here. Acquires ai0–ai3 | adds `SCAN_TISA_1, SCAN_TISA_2, SCAN_VEXLUM, VEXLUM, LIF_SHUTTER_OPEN` |
| `jim_DIO_acquire.py` | Minimal DIO + acquire test | `tYAG, ENH_start, ENH_end, tstart, tend` |

### Legacy reference (do NOT flag, do NOT archive)

`Just_Yag.py`, `BaF_scanning.py`, `BaF_Fluorescence_Raster.py` — lyman29-era sequences. Use COM12 instead of COM4, `NI_PCIe_6363` instead of `NI_PXIe_6361`, NuvuCamera, etc. Not compatible with active CT, kept intentionally as reference. Imports `labscriptlib.lyman29.subsequences`.

### Shared sub-sequence helpers (`subsequences/subsequences.py`)

- **`digital_pulse(digital_chan, tstart, tdur) → tend`** — `go_high(tstart)` / `go_low(tstart+tdur)`. The canonical DO pulse pattern.
- **`latch_digital(digital_chan, value) → None`** — `go_high(0)` / `go_low(0)` (time MUST be 0 because the NI_DAQmx worker reads `DO_table[0]` for the pre-latch value). For channels in `latched_lines`. See [[reference_ni-daqmx-latched-lines-three-layer-restore]].
- **`absorption_signal(ao_chan) → t`** — builds an absorption-dip waveform (sine4_reverse_ramp + sine_ramp). **Currently not called by any active sequence.**

## Sequence-writing idioms

### Scope trigger

```python
daq_ao0.constant(tstart, +2.5)
daq_ao0.constant(tstart + 0.5e-3, -2.5)   # falling edge → NI-5922 TRIG
```

The NI_SCOPE is configured `trigger_source='TRIG'`. Use `daq_ao0` (`ao0` on `ni_6361`) as the trigger output — never `daq_ao1`.

### DO even-padding

NI_DAQmx requires an EVEN number of DO children per port. Sequences add dummy pulses (often on `ENH_line`) purely to satisfy this. Comments throughout. If you add a new DO channel, audit the total DO count on its port for parity.

### Latched-line caveat

`latch_digital(LIF_shutter, value)` MUST be called with time=0 (no explicit timestamp passed) — the NI_DAQmx worker reads `DO_table[0]` for the pre-latch value. Calling at time != 0 means the latch sees a wrong starting state. Active only in `Closed_cell_scan.py`; commented out in `Open_cell.py` and `Closed_cell.py`.

## Globals model

- RunManager globals live in `Globals/BaF_globals.h5`, injected at compile time into **sequences only** — never the connection table.
- The CT has NO access to RunManager globals. `num_lasers=2` and `num_AI=6` are hardcoded in `connection_table.py` (this is a labscript-suite design constraint, not a fork issue).
- **"Undefined" globals in sequences are NOT bugs** — they're injected at compile time by RunManager (see `.claude/rules/sequences.md`). Static analysis will flag `TISA_1` etc. as undefined; ignore.
- **Naming inconsistency**: `Closed_cell.py` uses `ENH_START` / `ENH_DURATION`; `jim_DIO_acquire.py` uses `ENH_start` / `ENH_end`. Different globals, different sequences — no collision but two conventions.

## Connection-table backups (do not load)

- `connection_table_closed_cell.py` — older CT (COM7, `num_AI=4`, no remote GUIs, `dummy_line` line present, no NI_SCOPE).
- `connection_table_fromLyman.py` — Lyman-era CT (COM7, `NI_6361` `num_CI=1`, NuvuCamera, all remote/camera commented).
- `connection_table_photon_counting.py` — COM7 + `EdgeCounter` (`pulse_counter`, ctr0, PFI3, `sync_to_ai=True`) for photon counting.

**Do not assume any backup matches active hardware.** `num_AI`, COM port, device presence all differ. BLACS loads only `connection_table.py`.

## Shot-h5 path conventions (this experiment)

- **AI traces**: `/data/traces/{label}` — compound `(t, values)`, **t in seconds** (analysis scripts ×1000 → ms; `process_trace` expects ms). Labels: `Absorption0..3`, `Absorption_DC_Cell`, `Absorption_DC_Front` (Open_cell); `Absorption_DCprobe`, `Absorption`, `Absorption2`, `Absorption3` (Closed_cell_scan).
- **Scope traces**: `/data/traces/NI_SCOPE` — raw 2D float64 `(channels, samples)`. NaN-filled for unsaved channels (selective saving via `channels_to_save`).
- **Authoritative scan x-axis**: `/devices/LaserLockGUI/remote_device_operation['TiSa_1_Setpoint'][0]` (or whichever setpoint is being scanned). NOT `front_panel` or `monitor_values` — see `.claude/rules/analysis.md` and `docs/shot-h5-layout.md`.

## See also

- `docs/blacs-state-machine.md` — BLACS lifecycle (queued-shot semantics matter for `Closed_cell_scan.py`).
- `docs/remotecontrol-zmq-protocol.md` — how the three external GUIs are wired.
- `docs/external-guis-architecture.md` — per-GUI internals.
- `docs/shot-h5-layout.md` — exact shot-h5 structure.
- `.claude/rules/sequences.md` — sequence-writing rules incl. "undefined globals are not bugs".
- `.claude/rules/devices.md` — per-shot teardown + latched-lines invariants.
