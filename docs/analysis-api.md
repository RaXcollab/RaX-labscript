The analysis utility library in `userlib/analysislib/Main_Experiment/` provides reusable functions for lyse scripts and Jupyter notebooks:

- **`filtering.py`**: `process_trace()` (adaptive drift correction with slope check; deprecated kwargs `beforeYAG_time`, `after_abs_time`, `end_time` accepted with conversion), `smooth()`, `butter_lowpass_filter()`
- **`NI_SCOPE.py`**: `plot_ni_scope_channels()`, `load_ni_scope_sequences()` (auto-detects sample rate from h5 attrs), `ensure_time_ms()`, `_resolve_fs_hz()` (internal fallback chain)
- **`Abs_data.py`**: `load_sequence()` (threaded batch loader, warns on read failures and shape-mismatch drops), `extract_metadata()`

- **`scan_analysis.py`**: `load_scan_globals()` (per-shot expanded globals via lyse.Run), `load_scan_traces()` (threaded absorption-style trace loader), `load_scan_scope()` (NI_SCOPE batch loader), `group_and_subtract()` (shutter-interleaved background subtraction), `integrate_window()` (trapezoidal integration in time window), `baseline_correct_batch()` (batch wrapper for process_trace)

**API stability rule:** Analysis utility functions (`filtering.py`, `NI_SCOPE.py`, `Abs_data.py`, `scan_analysis.py`, and any future utility modules) must maintain backward compatibility. New features add new kwargs with defaults; existing parameters never change meaning or get removed. This ensures old notebooks that import from these modules continue to work. New notebooks should import from the utility library rather than redefining functions inline.

**Memory estimation rule:** Before bulk-loading trace arrays, estimate memory: `nshots × nsamples × 8 bytes`. Typical sizes per 744-shot scan: NI_SCOPE (200k samples) ≈ 1.2 GB, Absorption (40k samples) ≈ 0.24 GB. Flag anything >2 GB with a warning. Print the estimate so the user can decide whether to proceed or load a subset.

**Data path conventions:**
- Shot storage root: configure `experiment_shot_storage` in `labconfig/<computer-name>.ini`.
- Path structure: `{SequenceName}/YYYY/MM/DD/NNNN/` — top folder matches the sequence file name (e.g., `Closed_cell/` for `Closed_cell.py`)
- Shot files: `YYYY-MM-DD_NNNN_{SequenceName}_SSS.h5` (4-digit sequence, 3-digit shot)

**h5 trace layout:**
- Absorption traces (`Absorption`, `Absorption2`, `Absorption3`): structured dtype `(t, values)` at `data/traces/{name}`, shape `(nsamples,)`
- NI_SCOPE: raw 2D float64 `(nchan, nsamples)` at `data/traces/NI_SCOPE` with attrs `sample_rate`, `t0`, `channels_saved`

For analysis-specific questions, use the `lyse-analysis` agent for h5/trace/utility questions, and `amo-expert` for scan structure, globals expansion, and experiment design questions.
