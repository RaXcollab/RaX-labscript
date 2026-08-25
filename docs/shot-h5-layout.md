# Shot HDF5 contract

This document defines the current shot-file contract for the RaX reference apparatus.

Four writer stages can add data:

1. labscript writes the compiled shot definition.
2. RunManager writes evaluated globals.
3. BLACS writes front-panel state and acquired data.
4. lyse writes analysis results.

Readers must test optional paths before they read them.

## Top-level paths

| Path | Type and shape | Writer | Requirement |
|---|---|---|---|
| `/connection table` | Compound dataset, `(devices,)` | labscript; BLACS can replace it | Required for a valid shot |
| `/script` | Scalar byte dataset | labscript | Required |
| `/labscriptlib/...` | Scalar byte datasets | labscript | Present for embedded modules |
| `/globals/{group}` | Group; values are attributes | RunManager | Group content depends on the shot |
| `/globals/{group}/expansion` | Group; modes are attributes | RunManager | Optional per globals group |
| `/globals/{group}/units` | Group; units are attributes | RunManager | Optional per globals group |
| `/calibrations/{class}` | Class-specific compound dataset | labscript devices | Optional |
| `/shot_properties` | Group; properties are attributes | labscript | Required |
| `/time_markers` | Compound dataset, `(markers,)` | labscript | Required; it can be empty |
| `/waits` | Compound dataset, `(waits,)` | labscript | Required; it can be empty |
| `/front_panel` | Group | BLACS | Added after a completed run |
| `/devices/{device}` | Group | Device `generate_code()` | One group per compiled device |
| `/data` | Group | BLACS queue manager | Added after a completed run |
| `/images` | Group | Camera workers | Optional |
| `/results` | Group | lyse and result workers | Optional |

The root attribute `run time` identifies the BLACS run time. Repeat files can also have a `run repeat` attribute.

The queue manager uses `/data` as the completed-run marker. A device worker must not create `/data` before the shot ends.

The [queue manager](../blacs/blacs/experiment_queue.py) creates `/data` before it calls device post-experiment hooks.

## Front-panel state

The [front-panel writer](../blacs/blacs/front_panel_settings.py) creates `/front_panel` after the shot.

| Path | Type and shape | Optionality |
|---|---|---|
| `/front_panel/front_panel` | Compound dataset, `(channels,)` | Absent when no numeric channel rows exist |
| `/front_panel/_notebook_data` | Compound dataset, `(tabs,)` | Created for each front-panel write |

`/front_panel/front_panel` has these fields:

- `name`: byte string
- `device_name`: byte string
- `channel`: byte string
- `base_value`: float64
- `locked`: Boolean
- `base_step_size`: float64
- `current_units`: byte string

This dataset contains the BLACS state. It does not identify values that the shot script programmed.

`/front_panel/_notebook_data` has `tab_name`, `notebook`, `page`, `visible`, and `data` fields. Its attributes store window and plugin state.

## Compile-time device data

### RemoteControl devices

The [RemoteControl compiler](../userlib/user_devices/RemoteControl/labscript_devices.py) writes this dataset:

| Path | Type and shape | Optionality |
|---|---|---|
| `/devices/{device}/remote_device_operation` | Compound dataset, `(1,)`; one float64 field per connection | Present only for explicit `RemoteAnalogOut` values |

Each field name is a RemoteControl connection. Each value is the exact programmed setpoint.

The compiler omits the dataset when no child reports `value_set() == True`.

### NI-DAQmx devices

The [NI-DAQmx compiler](../labscript-devices/labscript_devices/NI_DAQmx/labscript_devices.py) writes the applicable datasets.

| Path | Type and shape | Optionality |
|---|---|---|
| `/devices/{device}/AO` | Compound dataset, `(samples,)`; float32 field per analog output | Present when analog outputs exist |
| `/devices/{device}/DO` | Compound dataset, `(samples,)`; integer field per digital port | Present when digital outputs exist |
| `/devices/{device}/AI` | Compound dataset, `(acquisitions,)` | Present when analog acquisitions exist |

Static output devices use one sample. Timed output devices use the pseudoclock sample count.

Each `DO` value packs all used lines of one port. The `AI` fields are `connection`, `label`, `start`, `stop`, `wait label`, `scale factor`, and `units`.

The device group has a `stop_time` attribute.

### PrawnBlaster devices

The [PrawnBlaster compiler](../labscript-devices/labscript_devices/PrawnBlaster/labscript_devices.py) writes one dataset per pseudoclock output.

| Path | Type and shape | Optionality |
|---|---|---|
| `/devices/{device}/PULSE_PROGRAM_{index}` | Compound dataset, `(instructions,)`; `half_period` and `reps` integer fields | One per configured pseudoclock output |

### Edge counter

The [edge-counter compiler](../userlib/user_devices/edge_counter/labscript_devices.py) stores its configuration as `/devices/{device}` attributes.

The attributes include `MAX_name`, `counter`, `pfi`, `edge`, `save_path`, and `sync_to_ai`.

## Post-shot device data

### RemoteControl monitor snapshots

The [RemoteControl worker](../userlib/user_devices/RemoteControl/blacs_workers.py) can write two monitor snapshots.

| Path | Type and shape | Capture point |
|---|---|---|
| `/data/{device}/monitor_values/initial_monitor_values` | Compound dataset, `(1,)`; float64 field per cached topic | After programming and before the shot |
| `/data/{device}/monitor_values/final_monitor_values` | Compound dataset, `(1,)`; float64 field per cached topic | In the post-experiment hook |

Each field name is a published monitor connection. The published value defines the field meaning.

The base worker reads both snapshots from its publish-subscribe cache. A value can lag the publisher by one publication interval.

The base worker writes no snapshot when the initial cache is empty. It also writes no snapshot without `remote_device_operation`.

The base worker writes no snapshots when communications are disabled. Abort paths clear both snapshots.

The initial and final datasets can have different fields. A monitor topic can appear or disappear between the two captures.

`BigSkyWorker` is an exception. It obtains the initial snapshot through `check_all_remote_values()` and the final snapshot from the publish-subscribe cache.

`BigSkyWorker` can write an initial snapshot without `remote_device_operation`. Its two snapshots can have different sources and meanings.

### Raster metadata

The [Rastering worker](../userlib/user_devices/RasteringDevice/blacs_workers.py) can create `/data/{device}/raster`.

This group contains attributes only. The allowed attributes are:

- `point_index`
- `path_len`
- `target_xy`
- `frame`
- `calibration_matrix`
- `calibration_offset`
- `in_place`

The worker writes only attributes returned by the raster controller. It omits the group outside raster mode or without raster metadata.

### NI-DAQmx traces

The [NI-DAQmx worker](../labscript-devices/labscript_devices/NI_DAQmx/blacs_workers.py) writes one dataset per acquisition label.

| Path | Type and shape | Optionality |
|---|---|---|
| `/data/traces/{label}` | Compound dataset, `(samples,)`; `t` float64 and `values` float32 | Present for completed analog acquisitions |

The label comes from `/devices/{device}/AI`. The worker omits trace datasets when no acquisition exists.

### NI scope traces

The [NI scope worker](../userlib/user_devices/NI_SCOPE/blacs_workers.py) writes one array for its device.

| Path | Type and shape | Optionality |
|---|---|---|
| `/data/traces/{device}` | Float64 array, `(channels, samples)` | Present after a successful fetch |

The dataset has `sample_rate`, `t0`, and `channels_saved` attributes. Unsaved channel rows contain `NaN` values.

### Measured waits

The active wait-monitor worker writes this dataset:

| Path | Type and shape | Optionality |
|---|---|---|
| `/data/waits` | Compound dataset, `(waits,)` | Present when the shot uses measured waits |

The fields are `label`, `time`, `timeout`, `duration`, and `timed_out`.

NI-DAQmx and PrawnBlaster wait monitors use the same path. A shot must have only one active writer for this dataset.

### Camera images

The [IMAQdx camera worker](../labscript-devices/labscript_devices/IMAQdxCamera/blacs_workers.py) and Nuvu worker use the same image layout.

| Path | Type and shape | Optionality |
|---|---|---|
| `/images/{orientation_or_device}/{exposure}/{frametype}` | Gzip-compressed uint16 image | Present when the camera save phase runs |

A single image has shape `(height, width)`. Repeated matching exposures have shape `(frames, height, width)`.

An expected exposure without a captured frame can produce an empty `(0,)` dataset. A failure before the save phase can omit the camera group.

The camera group has `camera` and `failed_shot` attributes. The image dataset has standard HDF5 grayscale-image attributes.

The [Nuvu worker](../userlib/user_devices/NuvuCamera/blacs_workers.py) also writes these scalar datasets:

- `/data/cam_info/detectorTemp`
- `/data/cam_info/rawEMGain`
- `/data/cam_info/calibratedEmGain`
- `/data/cam_info/exposureTime`
- `/data/cam_info/currentReadoutMode`

### Edge-counter result

The [edge-counter worker](../userlib/user_devices/edge_counter/blacs_workers.py) writes one scalar int64 dataset.

The default path is `/results/counter/total`. The device `save_path` attribute can select another path.

The worker creates parent groups and replaces an existing dataset at the selected path.

## Analysis results

lyse uses `/results/{script}` for each analysis script.

| Path | Type and shape | Writer |
|---|---|---|
| `/results/{script}` attributes | Scalar results | `save_result()` |
| `/results/{script}/{name}` | Analysis-defined dataset | `save_result_array()` |

Result types and shapes depend on the analysis script.

## Repeat-file rule

The queue manager copies only the immutable shot definition into a repeat file.

It copies `devices`, `calibrations`, `script`, `globals`, `connection table`, `labscriptlib`, `waits`, `time_markers`, and `shot_properties`.

It does not copy `front_panel`, `data`, `images`, or `results`. Their writers can create new values for the repeat.

## Reader rules and active limitations

- Use the exact `/connection table` name. The name contains a space.
- Test optional groups and datasets before access.
- Do not use `/front_panel/front_panel` as proof of a scripted setpoint.
- Do not assume that RemoteControl monitor snapshots exist.
- Do not assume that initial and final monitor fields match.
- Treat monitor values as cached samples, not synchronous measurements.
- Do not create `/data` from a device worker before the shot ends.
- Do not configure two wait-monitor writers for one shot.
