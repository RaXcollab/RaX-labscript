"""Build the interactive explorer notebook."""
import json, uuid, os

def uid():
    return uuid.uuid4().hex[:11]

def fix_src(text):
    parts = text.split('\n')
    return [p + '\n' if i < len(parts)-1 else p for i, p in enumerate(parts)]

def cell(ct, src, cid=None):
    c = {"cell_type": ct, "id": cid or uid(), "metadata": {}, "source": fix_src(src)}
    if ct == "code":
        c["execution_count"] = None
        c["outputs"] = []
    return c

# Get metadata from existing nb
ref = os.path.join(os.path.dirname(__file__), 'Closed_cell_03_05_2026.ipynb')
with open(ref) as f:
    meta = json.load(f)['metadata']

cells = [
    cell("markdown",
         "# Closed Cell Scan Explorer\n\n"
         "1. Run the **Setup** cell below (only needs to run once per kernel).\n"
         "2. Pick date + sequence, click **Detect Scan**, adjust dropdowns, click **Load & Process**.\n"
         "3. Explore with the cells below.\n\n"
         "First shot is auto-skipped (often bad). Pass `skip_first=False` in the Load call to keep it.\n"
         "Module auto-reloads on code changes — no kernel restart needed."),

    cell("code",
         "import sys\n"
         "sys.path.insert(0, '..')\n"
         "\n"
         "%load_ext autoreload\n"
         "%autoreload 3\n"
         "\n"
         "from scan_explorer_widgets import setup_explorer\n"
         "setup_explorer()\n"
         "# After clicking 'Load & Process', 'sa' is available in all cells below."),

    cell("markdown",
         "### 1. Overview \u2014 see all traces, pick integration bounds\n"
         "Shows every shot overlaid. Use this to see the signal range."),
    cell("code", "sa.overview()"),
    cell("code", "# Shutter closed comparison\n# sa.overview(shutter='closed')"),

    cell("markdown",
         "### 2. Interactive integration window picker\n"
         "Drag sliders to set bounds (fires on release). Read the title text,\n"
         "then pass to `spectroscopy(abs_int=(...), fl_int=(...))`."),
    cell("code", "sa.interactive_bounds()"),

    cell("markdown",
         "### 3. Spectroscopy\n"
         "Integrated signal vs scan variable.\n"
         "- `mode='shot'` (default): per-shot integration, mean \u00b1 std error bars\n"
         "- `mode='avg'`: average traces first, propagated error bars\n"
         "- Use `abs_int=(start, end)` and `fl_int=(start, end)` for separate bounds"),
    cell("code", "sa.spectroscopy()"),
    cell("code", "# Separate bounds, avg mode\n"
         "# sa.spectroscopy(abs_int=(0.05, 6.0), fl_int=(2.05, 12.0), mode='avg')"),

    cell("markdown", "### 4. Time traces\nAveraged OD and fluorescence vs time."),
    cell("code", "sa.time_traces()"),
    cell("code", "# Zoom in\n# sa.time_traces(xlim=(-0.5, 5))"),

    cell("markdown",
         "### 5. 2D Heatmaps\n"
         "Time vs scan variable. Tweak `t_range`, `shutter`, `secondary_filter`."),
    cell("code", "sa.heatmap()"),
    cell("code", "# Single secondary value, zoomed\n"
         "# sa.heatmap(t_range=(-0.5, 5), secondary_filter=[sa.sec_vals[0]])"),

    cell("markdown",
         "### 6. Single-point inspection\n"
         "Individual shots for a specific (scan, secondary) point."),
    cell("code", "# sa.single_trace(sa.scan_vals[15], sa.sec_vals[0], shutter=True)"),

    cell("code", ""),
]

nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": meta, "cells": cells}
out = os.path.join(os.path.dirname(__file__), 'Closed_cell_explorer.ipynb')
with open(out, 'w') as f:
    json.dump(nb, f, indent=1)
print(f'Wrote: {out}')
