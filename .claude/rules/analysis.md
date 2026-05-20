---
paths:
  - "userlib/analysislib/**"
---

# Analysis Conventions

## Do NOT Flag

- **NaN rows in NI_SCOPE h5 datasets** — unsaved channels are NaN-filled intentionally (selective saving), not data corruption
- **Deprecated kwargs in analysis utilities** — `beforeYAG_time`, `after_abs_time`, `end_time` are backward-compat aliases, not dead code
- **Inline function definitions in old Jupyter notebooks** — frozen analysis snapshots, not code duplication

## Import Constraints

- **`labscript_utils.h5_lock` must be imported before `h5py`** in any analysis module — lyse requires this ordering; violating it raises `ImportError`
- **lyse cannot be imported in worker threads** — zprocess signal handler requires main thread. Import lyse in the main thread, pass the module as an argument to workers
- **`lyse.Run.get_globals()`** returns expanded per-shot values for scanned globals (handles outer product expansion automatically)

## Authoritative Scan X-Axis

- **`/devices/{dev}/remote_device_operation['{ch}'][0]`** is the authoritative scan x-axis for any RemoteControl-programmed setpoint (full float64, the actual labscript intent for that shot).
- **Do NOT use** `front_panel`, `_AO/value`, or `monitor_values/initial_monitor_values` as the scan x-axis — they lag (quantized to widget display step), and `monitor_values` was `float32` before 2026-04-29 (≈40 MHz ULP at WS-scale THz → silently jagged spectra).
- **Wavemeter readings are PUB-SUB-only**, never persisted to the shot h5 — `LaserLockGUI`'s `*_monitor` connections appear in `monitor_values` only via the worker's drain snapshot, not as a separate dataset. For closed-cell scans, the setpoint is what to plot against.