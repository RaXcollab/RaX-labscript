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