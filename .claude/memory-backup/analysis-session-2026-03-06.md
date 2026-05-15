# Analysis Toolkit Session — 2026-03-06

## What was built
- `scan_plots.py` — `ScanAnalysis` class: load, process (OD + scope), plot
- `scan_explorer_widgets.py` — widget-based explorer (date/seq picker, detect scan, load)
- `_build_scan_notebooks.py` — generates static per-sequence notebooks
- `_build_explorer.py` — generates the interactive explorer notebook
- `Closed_cell_explorer.ipynb` — the main interactive notebook

## Key files
- `userlib/analysislib/Main_Experiment/scan_plots.py`
- `userlib/analysislib/Main_Experiment/scan_explorer_widgets.py`
- `userlib/analysislib/Main_Experiment/scan_analysis.py` (pre-existing utility)
- `userlib/analysislib/Main_Experiment/filtering.py` (pre-existing utility)
- `userlib/analysislib/Main_Experiment/Jupyter notebooks/Closed_cell_explorer.ipynb`
- `userlib/analysislib/Main_Experiment/Jupyter notebooks/Closed_cell_03_05_2026.ipynb` (original hand-edited)

## ScanAnalysis API
```python
sa = ScanAnalysis(folder, scan_col='TISA_1', secondary_col='V_YAG1',
                  skip_first=True, scope_offset_ms=0)
sa.overview()                          # all traces overlaid
sa.interactive_bounds()                # slider-based integration window picker
sa.spectroscopy(abs_int=(0.05, 6), fl_int=(2, 12), mode='shot')
sa.time_traces(xlim=(-1, 10))
sa.heatmap(t_range=(-1, 10), shutter='open')
sa.single_trace(sa.scan_vals[15], sa.sec_vals[0])
```

## Features implemented
- Beer-Lambert OD from drift-corrected absorption traces
- THz → MHz auto-conversion for frequency scan axes
- Per-shot error bars (mode='shot') and propagated error bars (mode='avg')
- Separate abs/fl integration windows
- Skip first shot (default on)
- Scope time offset parameter
- Shutter open/closed separate analysis (no bg subtraction)

## Architecture
- `load_scan_globals(folder)` loads ALL globals by default (no filter needed)
- `ScanAnalysis.__init__` only needs `scan_col`, `secondary_col` — everything else auto-detected
- Widget Load button injects `sa` into notebook namespace via `ip.user_ns['sa']`
- Experiment name exposed as editable widget in `setup_explorer(experiment='Closed_cell')`
- Scope pre-trigger auto-correction: `ref_position=1%` → 2ms offset (hardcoded in NI_SCOPE driver)

## Known issues / TODO
- **h5_lock import order** — `scan_explorer_widgets.py` must NOT import h5py at top level. Deferred inside `_detect_scan()`.
- **%autoreload 3** in notebook first cell handles code changes without kernel restart.
- **Widget idempotency** — `_state['widgets_created']` flag prevents duplicate button handlers on cell re-run.
- **Caching** — next priority. Save loaded traces as .npz + metadata as .json per sequence folder. Check h5 mtime vs cache mtime on load.
- **OD drift fit margins** (0.05 ms margin, 5 ms tail) hardcoded in `_compute_od` — could expose as params if needed.

## Data locations
- Closed cell data: `C:\Users\radmo\MIT Dropbox\...\Closed_cell\YYYY\MM\DD\SSSS\`
- Sequences analyzed: 03/05 seq 6, 03/06 seq 2/3/4/22
