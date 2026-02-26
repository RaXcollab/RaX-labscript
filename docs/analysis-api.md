The analysis utility library in `userlib/analysislib/Main_Experiment/` provides reusable functions for lyse scripts and Jupyter notebooks:

- **`filtering.py`**: `process_trace()` (adaptive drift correction with slope check; deprecated kwargs `beforeYAG_time`, `after_abs_time`, `end_time` accepted with conversion), `smooth()`, `butter_lowpass_filter()`
- **`NI_SCOPE.py`**: `plot_ni_scope_channels()`, `load_ni_scope_sequences()` (auto-detects sample rate from h5 attrs), `ensure_time_ms()`, `_resolve_fs_hz()` (internal fallback chain)
- **`Abs_data.py`**: `load_sequence()` (threaded batch loader, warns on read failures and shape-mismatch drops), `extract_metadata()`

**API stability rule:** Analysis utility functions (`filtering.py`, `NI_SCOPE.py`, `Abs_data.py`, and any future utility modules) must maintain backward compatibility. New features add new kwargs with defaults; existing parameters never change meaning or get removed. This ensures old notebooks that import from these modules continue to work. New notebooks should import from the utility library rather than redefining functions inline.

For analysis-specific questions, use the `lyse-analysis` agent. It knows the full utility API and the two analysis contexts: real-time lyse scripts (performance-critical) and offline Jupyter notebooks (thoroughness).
