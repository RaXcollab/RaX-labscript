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
│       'run time' set by BLACS at experiment_queue.py:915
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
│   │           (store_front_panel_in_h5, called from experiment_queue.py:908)
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
├── data/                         ── WRITTEN AFTER THE SHOT; SOME SUBGROUPS SHARED ──
│   │                                Writer: the queue manager creates the parent group once per
│   │                                shot at blacs/blacs/experiment_queue.py:913 — after the run,
│   │                                before any device post_experiment (dispatched at :938).
│   │                                Subgroups are written by device workers in post_experiment /
│   │                                transition_to_manual — never in transition_to_buffered:
│   │                                /data's presence IS BLACS's "shot has been run" marker (:387),
│   │                                so a worker creating it early makes an un-run file resubmit as
│   │                                a stripped _rep copy — and crashes the post-run bookkeeping
│   │                                AFTER the shot has already fired: front_panel (already saved
│   │                                at :908) is discarded by the error-path clean_h5_file copy,
│   │                                'run time' (:915) and every device's post_experiment write
│   │                                (:938) never happen, and the queue pauses.
│   │                                :913 is a bare create_group ON PURPOSE. That crash is the
│   │                                only detector for a device breaking this rule — it caught
│   │                                RasteringDevice within a day (2026-08-02). Fix the device,
│   │                                never soften :913. Durable guards: the /data invariant in
│   │                                .claude/rules/device-lifecycle.md and the RasteringDevice
│   │                                regression tests.
│   │                                Shared subgroup: traces/ (NI_DAQmx, NI_SCOPE, TekScope,
│   │                                AlazarTechBoard — each creates-if-absent). waits is a
│   │                                DATASET, not a group: exactly one wait-monitor device per
│   │                                shot creates /data/waits (NI_DAQmx :1222, PrawnBlaster :468,
│   │                                or Cicero :661 — unconditional create_dataset, so a second
│   │                                writer would raise).
│   │
│   ├── {RemoteControl device}/
│   │   └── monitor_values/                Writer: userlib/user_devices/RemoteControl/blacs_workers.py:714
│   │                                              (_save_monitor_values_to_hdf5, from post_experiment:687)
│   │       ├── initial_monitor_values     shape=(1,) compound  per-col dtype: float64
│   │       │                              (was float32 prior to 2026-04-29; see "Precision warning" below)
│   │       │                              Captured AFTER programming, BEFORE shot
│   │       │                              Source: blacs_workers.py:676 (_pubsub_cache snapshot in
│   │       │                              transition_to_buffered; written at :700)
│   │       └── final_monitor_values       shape=(1,) compound  per-col dtype: float64
│   │                                      Captured in post_experiment after the shot
│   │                                      Source: blacs_workers.py:693 (write at :703)
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
├── images/                       ── ONE SUBGROUP PER CAMERA ──
│   │                                Writer: IMAQdxCamera-family workers (and NuvuCamera) in
│   │                                transition_to_manual / post_experiment, writing each
│   │                                acquired exposure as a uint16 gzipped HDF5 IMAGE dataset.
│   │                                Source: labscript-devices/labscript_devices/IMAQdxCamera/
│   │                                blacs_workers.py:446-449 (the image_group lookup and dataset
│   │                                write). Group key is the camera's `orientation` property if
│   │                                set, else its device name.
│   │   image_group.attrs['camera']        ← device_name
│   │   image_group.attrs['failed_shot']   ← True if any exposure failed mid-shot
│   │
│   ├── {orientation_or_device_name}/
│   │   │   e.g. `images/side/`, `images/NuvuCamera/`
│   │   └── {exposure_name}/      ← per `expose(t, name, frametype, ...)` call
│   │       └── {frametype}       shape=(H, W) uint16   one dataset per (name, frametype)
│   │                             attrs: CLASS='IMAGE', IMAGE_VERSION='1.2',
│   │                                    IMAGE_SUBCLASS='IMAGE_GRAYSCALE',
│   │                                    IMAGE_WHITE_IS_ZERO=0
│   │                             (HDFView renders directly. Multiple exposures with the
│   │                             same (name, frametype) → stacked into a single dataset of
│   │                             shape (N, H, W) by the worker.)
│   │
│   └── (For NuvuCamera ONLY) — adds a sibling flat group
│       /data/cam_info/ holding per-shot scalar DATASETS {detectorTemp,
│       rawEMGain, calibratedEmGain, exposureTime, currentReadoutMode}
│       — no {device_name} level, no attrs. Written by
│       userlib/user_devices/NuvuCamera/blacs_workers.py:339-343 (post_experiment).
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

> **Lyse access pattern**: `df = lyse.data(); df['{orientation_or_device_name}/{exposure_name}', 'failed_shot']` returns the per-shot `failed_shot` attr column. Raw image bytes load via `lyse.Run(h5_path).get_image(orientation, name, frametype)` which is a thin wrapper around the same dataset path.

> **`failed_shot` is only written for PARTIAL acquisitions.** If the camera trigger never fires at all, `post_experiment` raises before the h5-write block, so the shot has **no `/images/{camera}` group and no `failed_shot` attr** — the lyse column is NaN/missing, not `True`. Analysis must therefore test **image-group presence** (`'images/NuvuCamera' in h5`), never the flag alone. Same rule for the 2026-07-06 open-cell data (103/223 run shots lack `/images/NuvuCamera`; none carry `failed_shot=True` because the tab died before the write). Semantics confirmed in the 2026-07-07 P3 (`fix/nuvu-214-retry`) consequence review — the 214-retry fix made missing-trigger failures loud but did not change what gets written.

## Where do I find setpoint X? (LaserLockGUI case study)

For LaserLockGUI, three places store frequency values per shot. **Two are setpoint-flavored; `monitor_values` holds the wavemeter measurement** — since the 2026-05-06 PUB-SUB-cache fix. Before that fix all three were setpoint-flavored and the wavemeter reading was not persisted anywhere; see "Known bugs" below.

### The visible BLACS GUI for LaserLockGUI

The custom `LaserLockTab` ([userlib/user_devices/LaserLockDevice/blacs_tabs.py](userlib/user_devices/LaserLockDevice/blacs_tabs.py)) shows two numbers per laser:
- **Setpoint spinbox** (user-editable) — backed by `self._AO[<port>]`, an output AnalogOutput, updated only by polling / restore / typing.
- **"Wavemeter:" QLabel** (read-only) — backed by `self._monitor_labels[<port>]`, a plain QLabel, updated only by PUB-SUB monitor messages from HF_Locking.

These are independent state. The setpoint AnalogOutput is **never updated by PUB-SUB**, and the wavemeter QLabel is **never read by the front-panel snapshot**. LaserLockTab explicitly avoids the base RemoteControlTab pattern of creating a second AnalogOutput for monitor connections — see the comment at [blacs_tabs.py:62-64](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L62) and the empty `self.AM_widgets = {}` at [line 82](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L82). For LaserLockGUI, `self._AO[<port>]` always means "the output (setpoint) AnalogOutput".

### The three persisted values

| Path | What it contains | Source |
|---|---|---|
| `/devices/LaserLockGUI/remote_device_operation['{ch}'][0]` | The **exact labscript-commanded setpoint** for this shot (the scan value, full float64) | Written by `RemoteControl.generate_code` from `RemoteAnalogOut.static_value` at compile time ([userlib/user_devices/RemoteControl/labscript_devices.py:286-291](userlib/user_devices/RemoteControl/labscript_devices.py#L286)). Only channels with `value_set()=True` appear. |
| `/front_panel/front_panel.base_value` (rows where `device_name=='LaserLockGUI'`) | The **HF_Locking server's stored setpoint as of the last periodic poll** — i.e., a slightly stale CHECK_VALUE response, possibly several seconds behind the current shot's commanded value | float64. Mechanism: `get_front_panel_values()` at [device_base_class.py:400-401](blacs/blacs/device_base_class.py#L400) returns `self._AO[conn].value`. For LaserLockTab, `self._AO[conn]` is the output AnalogOutput, updated by `_update_ao_widgets` ([LaserLockDevice/blacs_tabs.py:316-323](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L316)) from the periodic 5-s `check_remote_values` poll ([RemoteControl/blacs_tabs.py:357-371](userlib/user_devices/RemoteControl/blacs_tabs.py#L357)) which queries `CHECK_VALUE` ([blacs_workers.py:387](userlib/user_devices/RemoteControl/blacs_workers.py#L387)). Captured per shot at [experiment_queue.py:908](blacs/blacs/experiment_queue.py#L908). |
| `/data/LaserLockGUI/monitor_values/{initial,final}_monitor_values['{ch}'][0]` | The **wavemeter reading (`freq_display`) as of shot start and shot end** — the newest PUB-SUB sample held at each moment, so it lags the live stream by at most one publish period (HF_Locking publishes at 10 Hz, [workers.py:514-519](GUIs/HF_Locking/workers.py#L514)). Shots before 2026-05-06 hold the server's stored setpoint here instead — and **no shot found since 2026-05-07 actually carries these datasets (active Bug B below: the cache is empty in production, so the write is skipped)**. | per-column float64 (post-2026-04-29) / float32 (pre). Snapshotted from the worker's `_pubsub_cache` in `transition_to_buffered` ([blacs_workers.py:676](userlib/user_devices/RemoteControl/blacs_workers.py#L676)) and `post_experiment` ([:693](userlib/user_devices/RemoteControl/blacs_workers.py#L693)). The cache is filled by a daemon drain thread ([:462](userlib/user_devices/RemoteControl/blacs_workers.py#L462)) fed from the tab's PUB-SUB subscriber through the BLACS-internal EventBroker ([blacs_tabs.py:594](userlib/user_devices/RemoteControl/blacs_tabs.py#L594)). |

### Why all three differ even though all are "the setpoint" (April-2026 shots)

Empirical evidence from `Open_cell/2026/04/28/0015`, channel `'4'` (TiSa_1, ~348.666 THz, 5 MHz/shot scan). **These shots predate the 2026-05-06 fix, so `monitor_values` below is the server's stored setpoint** — in shots taken since, that column holds the wavemeter reading instead and this three-way setpoint comparison only applies to the other two datasets:

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

`/data/LaserLockGUI/monitor_values/{initial,final}_monitor_values` — since 2026-05-06 **by design; in practice no shot found since 2026-05-07 carries these datasets (active Bug B below)**. The HF_Locking server publishes `freq_display` per port over PUB-SUB on port 3797 ([HF_Locking/workers.py:514-519](GUIs/HF_Locking/workers.py#L514)); the LaserLockTab subscribes, displays it in `self._monitor_labels[conn]` ([LaserLockDevice/blacs_tabs.py:327-337](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L327)), and the base tab additionally forwards it into the BLACS-internal EventBroker ([RemoteControl/blacs_tabs.py:594](userlib/user_devices/RemoteControl/blacs_tabs.py#L594)) where the worker's drain thread caches it for the per-shot snapshots. It is still **not** in `/front_panel/front_panel` for LaserLockGUI (no monitor AnalogOutput exists). See "Known bugs" below.

### Other notes

- `remote_device_operation` is **not** the full list of setpoints — it only holds values the script explicitly programmed via `RemoteAnalogOut(...).constant(...)` (or equivalent). Channels controlled solely from the BLACS GUI still have a `front_panel.base_value` row but no `remote_device_operation` entry.
- **Channel ↔ name mapping**: only `/front_panel/front_panel` pairs the human name (`TiSa_1_Setpoint`) with the hardware channel (`'4'` in that shot; TiSa_1 is ch1 since 2026-07-29). The other two datasets use channel as the column key. Join through front_panel to translate.
- **This analysis is LaserLockGUI-specific.** See "RemoteControlTab vs LaserLockTab" below for how the general pattern works for BigSkyHub / RasteringGUI.

## RemoteControlTab vs LaserLockTab (inheritance + behavior)

`LaserLockTab` inherits from `RemoteControlTab` and overrides `initialise_GUI`. The single behavioral difference that matters for shot files: whether the tab calls `create_analog_outputs(AM_prop)` to create AnalogOutput backing for **monitor** connections.

| Base `RemoteControlTab` | LaserLockTab override |
|---|---|
| Calls `create_analog_outputs(AO_prop)` for outputs ([blacs_tabs.py:171](userlib/user_devices/RemoteControl/blacs_tabs.py#L171)) **and** `create_analog_outputs(AM_prop)` for monitors ([blacs_tabs.py:189](userlib/user_devices/RemoteControl/blacs_tabs.py#L189)) | Calls only the output one ([LaserLockDevice/blacs_tabs.py:76](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L76)). `self.AM_widgets = {}` empty. Wavemeter values land in plain QLabels (`self._monitor_labels`) instead. |
| `_on_monitor_value_received` writes PUB-SUB values into `self._AO[monitor_port].set_value(...)` ([blacs_tabs.py:578-592](userlib/user_devices/RemoteControl/blacs_tabs.py#L578)) | Override writes only to QLabel + recomputes error display ([LaserLockDevice/blacs_tabs.py:327-337](userlib/user_devices/LaserLockDevice/blacs_tabs.py#L327)) |
| If output and monitor share `parent_port`: the second `create_analog_outputs` overwrites `self._AO[<port>]` → output AnalogOutput is unreachable through `self._AO` | No overwrite possible (monitor AnalogOutputs not created) |

**Consequence for `front_panel/front_panel` rows** (verified empirically for shot 182):

| Device | Front_panel rows | Each row contains |
|---|---|---|
| LaserLockGUI | One per OUTPUT only (3/3 outputs, 0/2 monitors) | Server setpoint from last 5-s `CHECK_VALUE` poll |
| BigSkyLasers | One per output AND one per monitor (18/18 + 10/10) | Output rows: server setpoint from poll. Monitor rows: live PUB-SUB sensor reading at shot start. |
| RasteringGUI | Same as BigSky (2/2 + 2/2) | Same as BigSky |

For BigSky and Rastering, the scheme works because monitor `parent_port`s are distinct from output `parent_port`s (`YAG_1_voltage` vs `YAG_1_voltage_monitor`, `Raster_X` vs `Raster_X_Monitor`). For LaserLockGUI, output and monitor intentionally share `parent_port` so the spinbox and wavemeter label can be paired in the GUI — but that means the base-class `create_analog_outputs(AM_prop)` would clobber the output AnalogOutput, hence the LaserLockTab override.

**So the LaserLockGUI wavemeter reading is not in `front_panel`** — it lands in `/data/LaserLockGUI/monitor_values/` instead. For BigSky-style sensor readings per shot, look at `monitor` rows in `/front_panel/front_panel`.

## Known bugs (LaserLockGUI)

**Bug A — FIXED 2026-05-06: `initial_monitor_values` and `final_monitor_values` carried no temporal information.** Verified pre-fix: in scan 0015 channel `'4'`, 172/183 shots had `initial == final` *exactly*; the 11 divergent shots all differed by exactly +30.518 MHz (i.e., the setpoint was re-programmed mid-shot for those). The intent of the pre/post snapshot was to compare the **wavemeter measurement** before vs after the shot, so a drifted lock could be detected and the shot requeued. The old mechanism was `check_all_remote_values()` querying `CHECK_VALUE` over REQ-REP, which the HF_Locking server answers from `SharedExperimentState.setpoint` — a value that doesn't change unless someone reprograms it, so pre and post were identical except where the setpoint was changed mid-shot.

**How it was actually fixed** — worker-side subscription through the BLACS-internal EventBroker, *not* the tab-shared-`init_kwargs`-dict route originally sketched here:
1. `RemoteControlTab.connect_to_pubsub` lazily creates `Event(f'{device_name}_pubsub_monitor', role='post')` and connects `_post_to_internal_broker` to the monitor-value signal ([blacs_tabs.py:329-336](userlib/user_devices/RemoteControl/blacs_tabs.py#L329)). Every numeric PUB-SUB monitor value is posted into the broker with the connection as the event identifier ([blacs_tabs.py:594-611](userlib/user_devices/RemoteControl/blacs_tabs.py#L594)).
2. `RemoteControlWorker.init` opens the matching `role='wait'` Event and starts a daemon drain thread ([blacs_workers.py:434-456](userlib/user_devices/RemoteControl/blacs_workers.py#L434)) which writes `self._pubsub_cache[connection] = value` ([:478](userlib/user_devices/RemoteControl/blacs_workers.py#L478)) — bypassing `Event.wait()`'s identifier filter so all monitor channels land in one dict.
3. `transition_to_buffered` snapshots `dict(self._pubsub_cache)` into `initial_monitor_values` ([:676](userlib/user_devices/RemoteControl/blacs_workers.py#L676)); `post_experiment` does the same for `final_monitor_values` ([:693](userlib/user_devices/RemoteControl/blacs_workers.py#L693)).
4. `_save_monitor_values_to_hdf5` unchanged ([:714](userlib/user_devices/RemoteControl/blacs_workers.py#L714)).

So the LaserLockGUI snapshots now hold the **wavemeter reading** at shot start and shot end and do carry temporal information. `check_all_remote_values()` ([:581](userlib/user_devices/RemoteControl/blacs_workers.py#L581)) is no longer on the monitor_values path for the base worker.

**Residual (BigSkyLasers only): the pre/post pair is asymmetric.** `BigSkyWorker` overrides `transition_to_buffered` and still takes the *initial* snapshot via its own `check_all_remote_values()` ([BigSkyHub/blacs_workers.py:403](userlib/user_devices/BigSkyHub/blacs_workers.py#L403), and [:459](userlib/user_devices/BigSkyHub/blacs_workers.py#L459) for the no-`remote_device_operation` path), but inherits the base `post_experiment`, so the *final* snapshot comes from the PUB-SUB cache. The two datasets therefore have different column sets **and different meanings** — initial: REQ-REP `CHECK_VALUE` over outputs + monitors; final: PUB-SUB monitor topics only. LaserLockGUI and RasteringGUI are symmetric (both ends from the cache; [RasteringDevice/blacs_workers.py:264](userlib/user_devices/RasteringDevice/blacs_workers.py#L264)).

**Bug B — ACTIVE (found 2026-08-02): the worker's `_pubsub_cache` stays empty in production, so no `monitor_values` are written at all.** Evidence: BLACS.log 2026-08-02 logs `initial_monitor_values: 0 channels` on every shot for LaserLockGUI and RasteringGUI, and with an empty initial dict the gate at [blacs_workers.py:690](userlib/user_devices/RemoteControl/blacs_workers.py#L690) silently skips both writes. Empirically, ~12,500 run shots scanned 2026-05-07 → 2026-08-02 contain **zero** `/data/LaserLockGUI/monitor_values` (April shots have them — positive control `Open_cell/2026/04/28/0015`). So the Bug-A fix has never produced data in production: the drain-thread commit (f1298a3, 2026-05-06) is an ancestor of the running checkout, April shots carry the datasets, and every May shot scanned carries none. BigSkyLasers corroborates from a different angle: through 2026-07-22 it wrote **initial-only** datasets (11 columns incl. monitors — its *initial* bypasses the cache via REQ-REP `CHECK_VALUE`; the always-missing `final` shows the cache path was already dead pre-cutover on a day the GUI was demonstrably up). BigSky has written nothing since 2026-07-23 — possibly benign (an empty REQ-REP result also skips the write via the :690 gate, e.g. lasers disconnected). The drain threads start cleanly ("PUB-SUB drain thread started for N monitor channels", no errors) and the tab connects `_post_to_internal_broker` in `connect_to_pubsub` ([blacs_tabs.py:329-336](userlib/user_devices/RemoteControl/blacs_tabs.py#L329)), so the break is upstream of the cache: either `monitor_value_received` never fires in production (which would also freeze the GUI monitor labels and the `front_panel` monitor rows) or the tab→EventBroker→worker routing fails. Untriaged — tracked as a session task 2026-08-02.

## Monitor_values column rules (RemoteControl)

This is subtle. **Verified by reading the drain thread + snapshot path at [blacs_workers.py:462-494](userlib/user_devices/RemoteControl/blacs_workers.py#L462) / [:676](userlib/user_devices/RemoteControl/blacs_workers.py#L676) / [:693](userlib/user_devices/RemoteControl/blacs_workers.py#L693), the tab's forwarder at [blacs_tabs.py:531-558](userlib/user_devices/RemoteControl/blacs_tabs.py#L531) / [:594](userlib/user_devices/RemoteControl/blacs_tabs.py#L594), the connection table for `LaserLockGUI`, and the HF_Locking publisher at [GUIs/HF_Locking/workers.py:514-519](GUIs/HF_Locking/workers.py#L514).**

**Columns come from the PUB-SUB stream, not from the connection table.** The tab subscribes one SUB socket per entry in `child_monitor_connections` ([blacs_tabs.py:531-537](userlib/user_devices/RemoteControl/blacs_tabs.py#L531)), forwards each arriving `"<topic> <value>"` into the BLACS-internal EventBroker keyed by topic, and the worker's drain thread stores it as `_pubsub_cache[topic]`. A snapshot is a plain `dict()` copy of that cache, and `_save_monitor_values_to_hdf5` builds one float64 column per key present. Consequences:

- **Columns = the monitor `parent_port`s that have actually published at least once this worker session.** Outputs are *not* included (nothing subscribes to an output topic). A monitor whose topic never appears in the stream gets **no column at all** — not 0.0, not NaN. For BigSky that happens per laser: `HugeSkyController.pyw` skips broadcasting for any laser where `ctrl.isConnected()` is false, so a disconnected laser's monitor columns silently vanish from the snapshot. HF_Locking instead publishes `0.0` when `freq_display` is None ([workers.py:519](GUIs/HF_Locking/workers.py#L519)), so an unread port shows up as a `0.0` column.
- **If the cache is empty, no dataset is written at all** (early return at [blacs_workers.py:715](userlib/user_devices/RemoteControl/blacs_workers.py#L715)) — e.g. PUB-SUB down for the whole session, or a device with no `RemoteAnalogMonitor` children.
- **Duplicate `parent_port`s no longer collide.** An output and a monitor wrapping the same hardware channel share a `parent_port` (e.g. `TiSa_1_Setpoint` and `TiSa_1_Value` both have `parent_port='1'`), so `child_connections = child_output_connections + child_monitor_connections` ([blacs_workers.py:412](userlib/user_devices/RemoteControl/blacs_workers.py#L412)) still contains duplicates for LaserLockGUI (`['3', '1', '6', '1', '6']` — outputs Vexlum/TiSa_1/TiSa_2, then monitors TiSa_1_Value/TiSa_2_Value) — but that list only feeds `check_all_remote_values()` and the mock server now, not the snapshot path. Cache keys are monitor topics, so LaserLockGUI's snapshot columns are just `['1', '6']`.
- **The value is whatever that GUI publishes on that topic.** HF_Locking publishes `freq_display`, the wavemeter reading. BigSky publishes per-parameter sensor readings (`YAG_1_voltage_monitor` etc.). Rastering publishes live stage coordinates. Check the publisher, not the `CHECK_VALUE` handler, when generalizing to a new device.
- **BigSkyLasers `initial_monitor_values` is the exception** — it still comes from REQ-REP `CHECK_VALUE` over outputs + monitors (see "Known bugs" above), so for that device the initial dataset follows the *old* rules (unique parent_ports across outputs + monitors, duplicate-port collision, server-defined values) while the final dataset follows the rules above.
- **Snapshot freshness.** A snapshot is the newest sample the drain thread has stored, so it can lag a just-issued `PROGRAM_VALUE` by up to one publish period — ~250 ms for BigSky and Rastering (both ~4 Hz), ~100 ms for HF_Locking (10 Hz).

## Precision warning (RemoteControl, shots before 2026-04-29)

The `_save_monitor_values_to_hdf5` dtype was `np.float32` until it was changed to `np.float64` on 2026-04-29; it lives at [blacs_workers.py:718](userlib/user_devices/RemoteControl/blacs_workers.py#L718) today. The labscript-side `remote_device_operation` table has been `np.float64` throughout (set at [labscript_devices.py:286](userlib/user_devices/RemoteControl/labscript_devices.py#L286)).

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
| `/data/{device}/...` | per-device BLACS worker | `post_experiment` / queue-end `transition_to_manual` — never before the shot | float64 (RemoteControl, post-2026-04-29) |
| `/data/traces/...` | NI_DAQmx (`blacs_workers.py:902`) / NI_SCOPE | After shot | float64 |
| `/results/{script}/...` | lyse (`__init__.py:669, 679+`) | Post-shot in lyse | depends on analysis |

## Notes / gotchas

- **`/devices/{name}/remote_device_operation` is absent** if no `RemoteAnalogOut` for that device returned `value_set()=True` (early-exit at [labscript_devices.py:283-284](userlib/user_devices/RemoteControl/labscript_devices.py#L283)). The BLACS worker then early-exits and writes no `monitor_values` either.
- **For setpoints not programmed by the script**, read `/front_panel/front_panel`. Example: in shot 182, the LaserLockGUI script only programmed channel `'4'` (TiSa_1) — Vexlum and TiSa_2 were front-panel-only and appear nowhere in `/devices/` or `/data/` for that shot.
- **`/data/{name}/monitor_values/`** is absent if `enable_comms=False` on the BLACS tab for that device, or if the shot was aborted (snapshots cleared by `abort_*` methods at [blacs_workers.py:733-741](userlib/user_devices/RemoteControl/blacs_workers.py#L733)).
- **DO ports are atomic** — `/devices/{ni_device}/DO` has one compound column per *port* (e.g., `port0`); the column value packs all 8 lines on that port.
- **NI_SCOPE traces are NOT compound** — plain 2-D float64 array. Other AI traces ARE compound (`t`, `values`).
- **Connection-table snapshot at root** (`/connection_table`) is the version that actually ran; the source `.py` files are also embedded under `/labscriptlib/` for full reproducibility.
- **Repeat shots** copy the immutable groups (`devices`, `calibrations`, `script`, `globals`, `connection table`, `labscriptlib`, `waits`, `time_markers`, `shot_properties`) from the original via [experiment_queue.py:440-453](blacs/blacs/experiment_queue.py#L440); only `front_panel` and `data` are recaptured per repeat.
- **Empty `globals/{Group}` attrs**: if RunManager has the group but no globals were defined under it, the subgroup still exists (with empty `expansion/` and `units/`).
- **Early-aborted shots** may have `front_panel` and `remote_device_operation` absent (verified: `2026-04-21_0000_Open_cell_0.h5` has neither). Check for existence before reading.
