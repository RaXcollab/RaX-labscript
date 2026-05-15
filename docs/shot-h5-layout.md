# Shot HDF5 File Layout

Reference for what lives where in a per-shot h5 file. **Every claim cited to source.** Tree structure verified against `2026-04-28_0026_Open_cell_182.h5`. Device names match the `Main_Experiment` connection table on this machine.

A shot file is built up by three writers in sequence:
1. **labscript** at compile time — writes the immutable specification of the shot.
2. **RunManager** at compile time — writes globals.
3. **BLACS** at run time — adds front-panel state, opens the `data` group, and dispatches device workers (which write per-device readbacks).
4. **lyse** at analysis time — adds the `results` group.

## Top-level tree

```
shot_file.h5
│
├── /  (root attrs: 'n_runs', 'run number', 'run time', 'script_basename',
│                   'sequence_date', 'sequence_id', 'sequence_index')
│       'run time' set by BLACS at experiment_queue.py:903
│
├── connection_table              shape=(N_devices,) compound dtype
│                                 dtype: name|class|parent|parent port|
│                                        unit conversion class|unit conversion params|
│                                        BLACS_connection|properties
│   Writer 1: labscript at compile time
│             → site-packages/labscript/labscript.py:279
│             (function generate_connection_table, dtype defined at lines 272-275)
│   Writer 2: BLACS may rewrite if save_conn_table=True
│             → blacs/blacs/front_panel_settings.py:335
│
├── script                        scalar bytes — the main labscript .py file source
│                                 attrs: 'name' (basename), 'path' (dirname)
│   Writer:  labscript/labscript.py:395 (save_labscripts)
│
├── labscriptlib/                 ← embedded copies of every imported labscriptlib module
│   └── {package}/{module}.py     scalar bytes per module
│   Writer:  labscript/labscript.py:416 inside save_labscripts; loops over
│            sys.modules whose __file__ starts with the labscriptlib package prefix.
│
├── globals/                      ← one subgroup per RunManager globals group
│   ├── {GroupName}/  attrs={...} ← global VALUES are stored as the group's attrs
│   │                               (one attr per global, name=global, value=evaluated)
│   │   ├── expansion/  attrs     ← scan-expansion mode per global (zip/outer/etc.)
│   │   └── units/      attrs     ← display unit per global
│   Writer 1: labscript creates the empty 'globals' group (initial group creation)
│             → labscript/labscript.py:507
│   Writer 2: runmanager populates it
│             → site-packages/runmanager/__init__.py:127, 147
│   Read pattern: shot_utils.py:23 → for name, value in f['globals'].attrs.items()
│
├── calibrations/                 ← labscript output unit-conversion tables
│   └── {classname}                shape=(N,) compound, fields class-specific
│                                 (e.g., Shutter: name|open_delay|close_delay)
│   Writer 1: labscript creates empty group → labscript.py:511
│   Writer 2: per-output classes append rows → e.g., outputs.py:1607 (Shutter)
│
├── shot_properties/   attrs      ← per-shot scalar attrs (compiler.shot_properties)
│   Writer:  labscript/labscript.py:532-533
│
├── time_markers                  shape=(M,) compound[label, time(float64), color(1,3 int)]
│   Writer:  labscript/labscript.py:220 (save_time_markers); dtype line 216
│
├── waits                         shape=(W,) compound[label, time(float64), timeout(float64)]
│   Writer:  labscript/labscript.py:478 (generate_wait_table)
│
├── front_panel/                  ← BLACS GUI state captured PER SHOT
│   │   Writer: blacs/blacs/front_panel_settings.py:331-376
│   │           (store_front_panel_in_h5, called from experiment_queue.py:899)
│   ├── front_panel               shape=(N,) compound[name, device_name, channel,
│   │                                                  base_value(float64), locked(bool),
│   │                                                  base_step_size(float64),
│   │                                                  current_units]
│   │                             dtype defined at front_panel_settings.py:341
│   │                             ← Setpoint of EVERY output BLACS knows about (every device,
│   │                               every channel — not just RemoteControl). Includes
│   │                               channels NOT programmed by the script.
│   └── _notebook_data            shape=(K,) compound[tab_name, notebook, page, visible, data]
│                                 attrs: 'window_width', 'window_height', 'window_xpos', ...
│
├── devices/                      ── ONE SUBGROUP PER DEVICE ──
│   │                                Writer: each device's generate_code() at compile time.
│   │                                The empty parent group is created at labscript.py:510.
│   │                                The per-device group is created by Device.init_device_group
│   │                                at site-packages/labscript/base.py:480.
│   │
│   ├── {RemoteControl device}/   e.g., LaserLockGUI, BigSkyLasers, RasteringGUI
│   │   │   Writer: userlib/user_devices/RemoteControl/labscript_devices.py:290-291
│   │   │           (RemoteControl.generate_code; only emits if any RemoteAnalogOut child
│   │   │           returned value_set()=True at line 281)
│   │   └── remote_device_operation     shape=(1,) compound[<conn1>, <conn2>, ...]
│   │                                   dtype: float64 per column (line 286)
│   │                                   ← SETPOINTS the labscript script EXPLICITLY programmed.
│   │                                     Column key = the `connection` identifier passed to
│   │                                     RemoteAnalogOut(...). NOT the full setpoint list —
│   │                                     channels controlled only via BLACS GUI are absent.
│   │
│   ├── {NI_DAQmx device}/        e.g., ni_6361, ni_6535
│   │   │   Writer: labscript-devices/labscript_devices/NI_DAQmx/labscript_devices.py:617-624
│   │   │   attrs: 'stop_time' (line 618)
│   │   ├── AO                    shape=(N_samples,) compound[ao0, ao1, ...]   one column per AO line
│   │   ├── DO                    shape=(N_samples,) compound[port0, port1, ...]  one column per port
│   │   │                                 (DO writes are per-port atomic; column value packs all 8 lines)
│   │   └── AI                    shape=(N_acq,) compound[connection, label, start, ...]
│   │
│   ├── pb/                       PrawnBlaster pseudoclock
│   │   └── PULSE_PROGRAM_{N}     shape=(rows,) compound[half_period, reps]   per pseudoclock output
│   │
│   └── {acquisition-only}/       e.g., NI_SCOPE — empty group, attrs only
│
├── data/                         ── ONE SUBGROUP PER DEVICE ──
│   │                                Writer: BLACS creates the parent group ONCE per shot at
│   │                                blacs/blacs/experiment_queue.py:901. Per-device subgroups
│   │                                and datasets are written by individual device workers in
│   │                                transition_to_buffered / post_experiment.
│   │
│   ├── {RemoteControl device}/
│   │   └── monitor_values/                Writer: userlib/user_devices/RemoteControl/blacs_workers.py:382
│   │       ├── initial_monitor_values     shape=(1,) compound  per-col dtype: float64
│   │       │                              (was float32 prior to 2026-04-29; see "Precision warning" below)
│   │       │                              Captured AFTER programming, BEFORE shot
│   │       │                              Source: blacs_workers.py:350 (via check_all_remote_values
│   │       │                              at line 268; serialised at line 384)
│   │       └── final_monitor_values       shape=(1,) compound  per-col dtype: float64
│   │                                      Captured in post_experiment after the shot
│   │                                      Source: blacs_workers.py:356 (write at line 363)
│   │
│   │       ⚠ COLUMN SEMANTICS — important and non-obvious. See "Monitor_values column rules" below.
│   │
│   └── traces/                            ← AI traces (acquired waveforms)
│       │   Writer: NI_DAQmx (labscript-devices/labscript_devices/NI_DAQmx/blacs_workers.py:902,
│       │           in extract_measurements, called from post-shot data extraction)
│       │   The /data/traces group is created on first AI extraction (line 902).
│       ├── {label}                       shape=(samples,) compound[t, values]
│       │                                 one dataset per AI channel, named by labscript label
│       └── NI_SCOPE                      shape=(channels, samples) raw float64 (NOT compound)
│                                         Writer: userlib/user_devices/NI_SCOPE/blacs_workers.py
│
└── results/                      ── ONE SUBGROUP PER LYSE ANALYSIS SCRIPT ──
                                     Writer: lyse creates parent group on Run() instantiation
                                             → site-packages/lyse/__init__.py:287
                                     Per-script subgroups and contents are written by
                                     save_result (attr) → __init__.py:669
                                     save_result_array (dataset) → __init__.py:679+
    └── {script_basename}/        ← named after the analysis .py module (Run.group)
        ├── attrs                 ← from save_result(name, value)  (stored as group attrs)
        └── {array_name}          ← from save_result_array(name, data)  (stored as datasets)
```

## Where do I find setpoint X? (LaserLockGUI case study)

For LaserLockGUI, three places store frequency values per shot. **All three are setpoint-flavored, none is the wavemeter measurement.** The wavemeter reading is displayed in the BLACS GUI but **not persisted to any shot-file dataset**.

### The visible BLACS GUI for LaserLockGUI

The custom `LaserLockTab` ([userlib/user_devices/LaserLockDevice/blacs_tabs.py](userlib/user_devices/LaserLockDevice/blacs_tabs.py)) shows two numbers per laser:
- **Setpoint spinbox** (user-editable) — backed by `self._AO[<port>]`, an output AnalogOutput, updated only by polling / restore / typing.
- **"Wavemeter:" QLabel** (read-only) — backed by `self._monitor_labels[<port>]`, a plain QLabel, updated only by PUB-SUB monitor messages from HF_Locking.

These are independent state. The setpoint AnalogOutput is **never updated by PUB-SUB**, and the wavemeter QLabel is **never read by the front-panel snapshot**. LaserLockTab explicitly avoids the base RemoteControlTab pattern of creating a second AnalogOutput for monitor connections — see the comment at [blacs_tabs.py:62-64](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L62) and the empty `self.AM_widgets = {}` at [line 82](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L82). For LaserLockGUI, `self._AO[<port>]` always means "the output (setpoint) AnalogOutput".

### The three persisted values

| Path | What it contains | Source |
|---|---|---|
| `/devices/LaserLockGUI/remote_device_operation['{ch}'][0]` | The **exact labscript-commanded setpoint** for this shot (the scan value, full float64) | Written by `RemoteControl.generate_code` from `RemoteAnalogOut.static_value` at compile time ([userlib/user_devices/RemoteControl/labscript_devices.py:286-291](userlib/user_devices/RemoteControl/labscript_devices.py#L286)). Only channels with `value_set()=True` appear. |
| `/front_panel/front_panel.base_value` (rows where `device_name=='LaserLockGUI'`) | The **HF_Locking server's stored setpoint as of the last periodic poll** — i.e., a slightly stale CHECK_VALUE response, possibly several seconds behind the current shot's commanded value | float64. Mechanism: `get_front_panel_values()` at [device_base_class.py:400-401](blacs/blacs/device_base_class.py#L400) returns `self._AO[conn].value`. For LaserLockTab, `self._AO[conn]` is the output AnalogOutput, updated by `_update_ao_widgets` ([LaserLockDevice/blacs_tabs.py:316-323](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L316)) from the periodic 5-s `check_remote_values` poll ([RemoteControl/blacs_tabs.py:295-323](userlib/user_devices/RemoteControl/blacs_tabs.py#L295)) which queries `CHECK_VALUE` ([blacs_workers.py:250-266](userlib/user_devices/RemoteControl/blacs_workers.py#L250)). Captured per shot at [experiment_queue.py:899](blacs/blacs/experiment_queue.py#L899). |
| `/data/LaserLockGUI/monitor_values/{initial,final}_monitor_values['{ch}'][0]` | The **HF_Locking server's stored setpoint immediately after this shot's PROGRAM_VALUE** — and (per "Known bugs" below) the same value pre and post | per-column float64 (post-2026-04-29) / float32 (pre). Captured via REQ-REP `CHECK_VALUE` in `check_all_remote_values()` ([blacs_workers.py:268-281](userlib/user_devices/RemoteControl/blacs_workers.py#L268)). Server handler at [HF_Locking/workers.py:559-562](GUIs/HF_Locking/workers.py#L559) returns `st.get("setpoint", 0.0)` — the server's record of the most recently programmed value, possibly quantized by the DLL decimal-string round-trip. |

### Why all three differ even though all are "the setpoint"

Empirical evidence from `Open_cell/2026/04/28/0015`, channel `'4'` (TiSa_1, ~348.666 THz, 5 MHz/shot scan):

Shot 011:
- `remote_device_operation['4']` = `348.6663020` (labscript intent — exact float64)
- `monitor_values/initial['4']` = `348.6662903` (server setpoint after this shot's programming — **−11.7 MHz** vs intent, DLL round-trip)
- `front_panel.base_value` for ch `'4'` = `348.6662920` (server setpoint from last poll — **+1.7 MHz** vs `monitor_values/initial`)

Shots 010 and 011 have **identical** `monitor_values` (348.6662903) AND **identical** `front_panel.base_value` (348.6662920), even though `remote_device_operation` increments by 5 MHz. The HF_Locking server's stored setpoint is not changing every shot — likely a deadband or DLL precision floor in `PROGRAM_VALUE`. So:
- `remote_device_operation` walks the scan in true 5 MHz steps (labscript intent).
- `monitor_values` and `front_panel` lag/quantize to ~10–30 MHz steps based on what actually got accepted by the server.

In scan 0015 across 183 shots, 132/183 had `front_panel ≠ remote_device_operation`, quantized to multiples of ~5 MHz, ranging up to −295 MHz mismatch on shots where the scan jumped between blocks faster than the poll could catch up.

**For scan analysis, use `remote_device_operation` as the authoritative x-axis** — it is the only value not subject to server-side quantization or polling lag.

### Where to find the wavemeter reading

It's not in the shot file. The HF_Locking server publishes `freq_display` over PUB-SUB on port 3797 ([HF_Locking/workers.py:486-489](GUIs/HF_Locking/workers.py#L486)), the LaserLockTab subscribes and displays it in `self._monitor_labels[conn]`, and that's the end of the data path. To capture it per-shot, see "Known bugs" below.

### Other notes

- `remote_device_operation` is **not** the full list of setpoints — it only holds values the script explicitly programmed via `RemoteAnalogOut(...).constant(...)` (or equivalent). Channels controlled solely from the BLACS GUI still have a `front_panel.base_value` row but no `remote_device_operation` entry.
- **Channel ↔ name mapping**: only `/front_panel/front_panel` pairs the human name (`TiSa_1_Setpoint`) with the hardware channel (`'4'`). The other two datasets use channel as the column key. Join through front_panel to translate.
- **This analysis is LaserLockGUI-specific.** See "RemoteControlTab vs LaserLockTab" below for how the general pattern works for BigSkyHub / RasteringGUI.

## RemoteControlTab vs LaserLockTab (inheritance + behavior)

`LaserLockTab` inherits from `RemoteControlTab` and overrides `initialise_GUI`. The single behavioral difference that matters for shot files: whether the tab calls `create_analog_outputs(AM_prop)` to create AnalogOutput backing for **monitor** connections.

| Base `RemoteControlTab` | LaserLockTab override |
|---|---|
| Calls `create_analog_outputs(AO_prop)` for outputs ([blacs_tabs.py:133](userlib/user_devices/RemoteControl/blacs_tabs.py#L133)) **and** `create_analog_outputs(AM_prop)` for monitors ([blacs_tabs.py:151](userlib/user_devices/RemoteControl/blacs_tabs.py#L151)) | Calls only the output one ([LaserLockDevice/blacs_tabs.py:76](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L76)). `self.AM_widgets = {}` empty. Wavemeter values land in plain QLabels (`self._monitor_labels`) instead. |
| `_on_monitor_value_received` writes PUB-SUB values into `self._AO[monitor_port].set_value(...)` ([blacs_tabs.py:478-486](userlib/user_devices/RemoteControl/blacs_tabs.py#L478)) | Override writes only to QLabel + recomputes error display ([LaserLockDevice/blacs_tabs.py:327-337](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L327)) |
| If output and monitor share `parent_port`: the second `create_analog_outputs` overwrites `self._AO[<port>]` → output AnalogOutput is unreachable through `self._AO` | No overwrite possible (monitor AnalogOutputs not created) |

**Consequence for `front_panel/front_panel` rows** (verified empirically for shot 182):

| Device | Front_panel rows | Each row contains |
|---|---|---|
| LaserLockGUI | One per OUTPUT only (3/3 outputs, 0/2 monitors) | Server setpoint from last 5-s `CHECK_VALUE` poll |
| BigSkyLasers | One per output AND one per monitor (18/18 + 10/10) | Output rows: server setpoint from poll. Monitor rows: live PUB-SUB sensor reading at shot start. |
| RasteringGUI | Same as BigSky (2/2 + 2/2) | Same as BigSky |

For BigSky and Rastering, the scheme works because monitor `parent_port`s are distinct from output `parent_port`s (`YAG_1_voltage` vs `YAG_1_voltage_monitor`, `Raster_X` vs `Raster_X_Monitor`). For LaserLockGUI, output and monitor intentionally share `parent_port` so the spinbox and wavemeter label can be paired in the GUI — but that means the base-class `create_analog_outputs(AM_prop)` would clobber the output AnalogOutput, hence the LaserLockTab override.

**So if you want the wavemeter reading per shot for LaserLockGUI, it isn't there.** For BigSky-style sensor readings per shot, look at `monitor` rows in `/front_panel/front_panel`.

## Known bugs (LaserLockGUI, as of 2026-05-01)

**Bug A: `initial_monitor_values` and `final_monitor_values` carry no temporal information.** Verified: in scan 0015 channel `'4'`, 172/183 shots had `initial == final` *exactly*; the 11 divergent shots all differed by exactly +30.518 MHz (i.e., the setpoint was re-programmed mid-shot for those). The intent of the pre/post snapshot was to compare the **wavemeter measurement** before vs after the shot, so a drifted lock could be detected and the shot requeued (TODO at [blacs_workers.py:306](userlib/user_devices/RemoteControl/blacs_workers.py#L306)). What actually happens: `check_all_remote_values()` queries `CHECK_VALUE` over REQ-REP, which the HF_Locking server answers from `SharedExperimentState.setpoint` — a value that doesn't change unless someone reprograms it. So pre and post are identical except in shots where the setpoint was changed mid-shot.

**Fix path:** capture the cached PUB-SUB `freq_display` value at the right moments. For LaserLockTab specifically, this is *not* available through `self._AO` (no AM AnalogOutput exists — see "RemoteControlTab vs LaserLockTab" above). Concrete fix:
1. Add a `dict` to LaserLockTab keyed by connection, e.g. `self._latest_pubsub_values = {conn: None for conn in self.child_monitor_connections}`.
2. Have `_on_monitor_value_received` write into that dict (in addition to updating `_monitor_labels[conn]`).
3. Pass a reference to that dict into the worker via `init_kwargs` in `initialise_workers` (the tab-worker shared-dict pattern is already used elsewhere — see auto-memory note "Tab-worker shared dict for PUB-SUB cache").
4. In the worker's `transition_to_buffered`, snapshot `dict(self._pubsub_cache)` into `self.initial_monitor_values` instead of calling `check_all_remote_values()`. Same in `post_experiment` for `self.final_monitor_values`.
5. Keep `_save_monitor_values_to_hdf5` unchanged.

For BigSkyHub / RasteringGUI (using base RemoteControlTab), the equivalent of step 4 already works "for free" via the `monitor` rows in `/front_panel/front_panel` (which capture the AM AnalogOutput value at shot start). They don't have this bug — but they also don't get a separate post-shot snapshot, since front_panel only fires once per shot.

## Monitor_values column rules (RemoteControl)

This is subtle. **Verified by reading [blacs_workers.py:268-281](userlib/user_devices/RemoteControl/blacs_workers.py#L268), the connection table for `LaserLockGUI`, and the HF_Locking server's REP handler at [GUIs/HF_Locking/workers.py:559-562](GUIs/HF_Locking/workers.py#L559).**

The worker computes `child_connections = child_output_connections + child_monitor_connections` ([blacs_workers.py:216](userlib/user_devices/RemoteControl/blacs_workers.py#L216)). Both lists hold `parent_port` strings. **An output and a monitor that wrap the same hardware channel share the same `parent_port`** (e.g., `TiSa_1_Setpoint` and `TiSa_1_Value` both have `parent_port='4'`). So `child_connections` contains duplicates for LaserLockGUI: `['4', '6', '3', '4', '6']`.

`check_all_remote_values()` iterates this list and sends `CHECK_VALUE` to the server for each entry, storing responses in a Python dict keyed by `connection`. Duplicates collide — outputs are queried first, monitors second — but for HF_Locking it doesn't matter which query "wins" because the server returns the same value for the same `connection` regardless of whether the labscript-side caller was an output or a monitor.

**What HF_Locking's server returns for `CHECK_VALUE`** ([workers.py:559-562](GUIs/HF_Locking/workers.py#L559)):
```python
if action == "CHECK_VALUE":
    p = int(d["connection"])
    st = self.state.get_status(p)
    return json.dumps({"status": "SUCCESS", "value": st.get("setpoint", 0.0)})
```
→ The **server-side stored setpoint** (DLL readback into `SharedExperimentState`), NOT the wavemeter measurement. This is "what HF_Locking believes the laser is locked to", which may differ from the labscript intent because of DLL/decimal-string round-trip quantization, and from the wavemeter measurement because of laser drift / lock error.

**Practical implications:**
- The columns of `{initial,final}_monitor_values` = the unique parent_ports across that device's outputs + monitors (NOT the labscript connection names; NOT the human-readable setpoint names).
- For LaserLockGUI specifically, the value in each column is the HF_Locking server's stored setpoint at the moment of the REQ-REP query — it is *not* a wavemeter reading. The wavemeter reading lives in `/front_panel/front_panel` instead (via PUB-SUB; see "Where do I find setpoint X?").
- If a device has no `RemoteAnalogMonitor` children, `final_monitor_values` is just the output-readback (one query per output, no duplicate-port overwrite — but the value is still server-defined).
- For non-LaserLockGUI devices (BigSkyHub, RasteringGUI, etc.), what the server returns is *that* server's choice. Verify each REP handler before generalizing.

## Precision warning (RemoteControl, shots before 2026-04-29)

The `_save_monitor_values_to_hdf5` dtype was `np.float32` until [blacs_workers.py:374](userlib/user_devices/RemoteControl/blacs_workers.py#L374) was changed to `np.float64`. The labscript-side `remote_device_operation` table has been `np.float64` throughout (set at [labscript_devices.py:286](userlib/user_devices/RemoteControl/labscript_devices.py#L286)).

For wavemeter-scale frequencies (~10⁵ MHz), float32 ULP is ~40 MHz, so `monitor_values` snapshots in older shots are unreliable for sub-MHz analysis. Programmed setpoints in `remote_device_operation` are full float64 precision in all shots.

## Quick read recipes (lyse / Jupyter)

```python
import labscript_utils.h5_lock  # MUST come before h5py
import h5py

with h5py.File(shot_h5, 'r') as f:
    # All BLACS setpoints at shot start (every device, with units + names)
    fp = f['/front_panel/front_panel'][:]
    laser_rows = fp[fp['device_name'] == b'LaserLockGUI']
    for r in laser_rows:
        print(r['name'].decode(), '=', r['base_value'], r['current_units'].decode())

    # RemoteControl: programmed setpoint vs readback (script-set channels only)
    setpoint = f['/devices/LaserLockGUI/remote_device_operation']['<channel>'][0]
    pre  = f['/data/LaserLockGUI/monitor_values/initial_monitor_values']['<channel>'][0]
    post = f['/data/LaserLockGUI/monitor_values/final_monitor_values']['<channel>'][0]

    # NI_DAQmx AI trace
    trace = f['/data/traces/Absorption0']
    t, y = trace['t'], trace['values']

    # NI_SCOPE waveform (raw 2-D float64 array, NOT compound)
    scope = f['/data/traces/NI_SCOPE'][:]    # shape (channels, samples)

    # RunManager global value (stored as group attr)
    yag_energy = f['/globals/YAG Energy'].attrs['<global_name>']

    # lyse analysis result (scalar)
    fitted = f['/results/<script_basename>'].attrs['<result_name>']

    # lyse analysis result (array)
    arr = f['/results/<script_basename>/<array_name>'][:]
```

## Patterns at a glance

| Section | Writer | When | Trustworthy precision |
|---|---|---|---|
| `/connection_table` | labscript (`labscript.py:279`) or BLACS (`front_panel_settings.py:335`) | Compile time / per-shot rewrite | n/a |
| `/script`, `/labscriptlib/...` | labscript (`labscript.py:395, 416`) | Compile time | n/a |
| `/calibrations/{Class}` | labscript output classes (e.g., `outputs.py:1607` Shutter) | Compile time | float64 (per dtype) |
| `/globals/{Group}` attrs | runmanager (`__init__.py:147`) | Compile time | Python type-preserved (attrs) |
| `/shot_properties/` attrs | labscript (`labscript.py:532-533`) | Compile time | n/a |
| `/time_markers`, `/waits` | labscript (`labscript.py:220, 478`) | Compile time | float64 |
| `/front_panel/front_panel` | BLACS (`front_panel_settings.py:376`) | Per-shot, before run | float64 (`base_value`) |
| `/devices/{name}/...` | per-device labscript `generate_code` | Compile time | float64 (RemoteControl), per-device for others |
| `/data/{device}/...` | per-device BLACS worker | `transition_to_buffered` / `post_experiment` | float64 (RemoteControl, post-2026-04-29) |
| `/data/traces/...` | NI_DAQmx (`blacs_workers.py:902`) / NI_SCOPE | After shot | float64 |
| `/results/{script}/...` | lyse (`__init__.py:669, 679+`) | Post-shot in lyse | depends on analysis |

## Notes / gotchas

- **`/devices/{name}/remote_device_operation` is absent** if no `RemoteAnalogOut` for that device returned `value_set()=True` (early-exit at [labscript_devices.py:283-284](userlib/user_devices/RemoteControl/labscript_devices.py#L283)). The BLACS worker then early-exits and writes no `monitor_values` either.
- **For setpoints not programmed by the script**, read `/front_panel/front_panel`. Example: in shot 182, the LaserLockGUI script only programmed channel `'4'` (TiSa_1) — Vexlum and TiSa_2 were front-panel-only and appear nowhere in `/devices/` or `/data/` for that shot.
- **`/data/{name}/monitor_values/`** is absent if `enable_comms=False` on the BLACS tab for that device, or if the shot was aborted (snapshots cleared by `abort_*` methods at [blacs_workers.py:389-397](userlib/user_devices/RemoteControl/blacs_workers.py#L389)).
- **DO ports are atomic** — `/devices/{ni_device}/DO` has one compound column per *port* (e.g., `port0`); the column value packs all 8 lines on that port.
- **NI_SCOPE traces are NOT compound** — plain 2-D float64 array. Other AI traces ARE compound (`t`, `values`).
- **Connection-table snapshot at root** (`/connection_table`) is the version that actually ran; the source `.py` files are also embedded under `/labscriptlib/` for full reproducibility.
- **Repeat shots** copy the immutable groups (`devices`, `calibrations`, `script`, `globals`, `connection table`, `labscriptlib`, `waits`, `time_markers`, `shot_properties`) from the original via [experiment_queue.py:440-453](blacs/blacs/experiment_queue.py#L440); only `front_panel` and `data` are recaptured per repeat.
- **Empty `globals/{Group}` attrs**: if RunManager has the group but no globals were defined under it, the subgroup still exists (with empty `expansion/` and `units/`).
- **Early-aborted shots** may have `front_panel` and `remote_device_operation` absent (verified: `2026-04-21_0000_Open_cell_0.h5` has neither). Check for existence before reading.
