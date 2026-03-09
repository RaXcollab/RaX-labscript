"""Generate parameterized closed-cell scan analysis notebooks."""
import json, os, uuid

def uid():
    return uuid.uuid4().hex[:11]

def fix_src(text):
    parts = text.split('\n')
    result = []
    for i, p in enumerate(parts):
        if i < len(parts) - 1:
            result.append(p + '\n')
        else:
            result.append(p)
    return result

def make_cell(cell_type, source, cell_id=None):
    c = {
        "cell_type": cell_type,
        "id": cell_id or uid(),
        "metadata": {},
        "source": fix_src(source),
    }
    if cell_type == "code":
        c["execution_count"] = None
        c["outputs"] = []
    return c

# Read metadata from existing notebook
src = os.path.join(os.path.dirname(__file__), 'Closed_cell_03_05_2026.ipynb')
with open(src) as f:
    meta = json.load(f)['metadata']

# ---- Build generic cells ----
IMPORTS = """\
import sys, os
sys.path.insert(0, os.path.abspath('..'))

import numpy as np
import matplotlib.pyplot as plt
from scan_analysis import (
    load_scan_globals, load_scan_traces, load_scan_scope,
    integrate_window
)
from filtering import line_func
from scipy.optimize import curve_fit"""

LOAD_GLOBALS = """\
df = load_scan_globals(SEQ_FOLDER, GLOBAL_NAMES)

tYAG_MS = float(df['tYAG'].iloc[0]) * 1000
tstart_MS = float(df['tstart'].iloc[0]) * 1000
ABS_INT_START = tYAG_MS + ABS_OFFSET_START
ABS_INT_END = tYAG_MS + ABS_OFFSET_END
SCOPE_INT_START = tYAG_MS + SCOPE_OFFSET_START
SCOPE_INT_END = tYAG_MS + SCOPE_OFFSET_END

scan_vals = sorted(df[SCAN_COL].unique())
sec_vals = sorted(df[SECONDARY_COL].unique())

# Auto-detect THz frequency and convert to MHz offset for display
_sv = np.array(scan_vals)
if len(_sv) > 1 and np.min(_sv) > 100 and np.ptp(_sv) < 0.01:
    scan_ref = np.min(_sv)
    scan_display = (_sv - scan_ref) * 1e6  # MHz
    scan_label = f'{SCAN_COL} - {scan_ref:.6f} THz [MHz]'
else:
    scan_ref = None
    scan_display = _sv
    scan_label = SCAN_COL

print(f"Shape: {df.shape}")
print(f"tstart = {tstart_MS} ms, tYAG = {tYAG_MS} ms")
print(f"{SCAN_COL}: {len(scan_vals)} unique")
if scan_ref: print(f"  Display: offset from {scan_ref:.6f} THz in MHz")
print(f"{SECONDARY_COL}: {sec_vals}")
print(f"{SHUTTER_COL}: {df[SHUTTER_COL].value_counts().to_dict()}")
df.head()"""

LOAD_TRACES = """\
abs_data = load_scan_traces(SEQ_FOLDER, ABS_TRACE, df=df)
abs_time_ms = abs_data['time'] * 1000

scope_data = load_scan_scope(SEQ_FOLDER, ch=SCOPE_CH, df=df)"""

BASELINE_OD = """\
# --- Absorption: drift correction then Beer-Lambert OD ---
trig_idx_abs = np.searchsorted(abs_time_ms, tYAG_MS)
before_mask = abs_time_ms < (tYAG_MS - 0.05)
after_mask = abs_time_ms > (abs_time_ms[-1] - 5.0)

abs_OD = np.zeros_like(abs_data['data'])
for i in range(abs_data['data'].shape[0]):
    raw = abs_data['data'][i]
    if np.all(np.isnan(raw)):
        continue
    fit_t = np.concatenate((abs_time_ms[before_mask], abs_time_ms[after_mask]))
    fit_v = np.concatenate((raw[before_mask], raw[after_mask]))
    if len(fit_t) < 5:
        continue
    popt, _ = curve_fit(line_func, fit_t, fit_v, p0=[0, np.mean(fit_v)])
    detrended = raw - popt[0] * abs_time_ms
    I0 = np.mean(detrended[:trig_idx_abs])
    with np.errstate(divide='ignore', invalid='ignore'):
        od = -np.log(detrended / I0)
    abs_OD[i] = np.where(np.isfinite(od), od, 0.0)

print(f"Absorption OD: post-YAG range = "
      f"{np.nanmin(abs_OD[:, trig_idx_abs:]):.4f} to {np.nanmax(abs_OD[:, trig_idx_abs:]):.4f}")

# --- Scope ---
scope_time_ms = scope_data['time_ms']
scope_trig_idx = np.searchsorted(scope_time_ms, tYAG_MS)
scope_baseline = np.nanmean(scope_data['data'][:, :scope_trig_idx], axis=1, keepdims=True)
scope_corrected = scope_data['data'] - scope_baseline

avg_fl = np.nanmean(np.abs(scope_corrected), axis=0)
peak_idx = np.argmax(avg_fl[scope_trig_idx:]) + scope_trig_idx
print(f"Fluorescence peak at scope_time = {scope_time_ms[peak_idx]:.2f} ms (expect ~ {tYAG_MS:.1f} ms)")"""

SPECTROSCOPY = """\
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
ax_abs_open, ax_abs_closed, ax_fl = axes

for sv in sec_vals:
    xd, abs_oi, abs_ci, fl_oi, fl_ci = [], [], [], [], []
    for xi, xv in enumerate(scan_vals):
        om = (df[SHUTTER_COL] == True) & (df[SCAN_COL] == xv) & (df[SECONDARY_COL] == sv)
        cm = (df[SHUTTER_COL] == False) & (df[SCAN_COL] == xv) & (df[SECONDARY_COL] == sv)
        oi, ci = df.index[om].tolist(), df.index[cm].tolist()
        if not oi:
            continue
        xd.append(scan_display[xi])
        abs_oi.append(integrate_window(abs_time_ms, np.mean(abs_OD[oi], axis=0)[None,:], ABS_INT_START, ABS_INT_END)[0])
        fl_oi.append(-integrate_window(scope_time_ms, np.mean(scope_corrected[oi], axis=0)[None,:], SCOPE_INT_START, SCOPE_INT_END)[0])
        if ci:
            abs_ci.append(integrate_window(abs_time_ms, np.mean(abs_OD[ci], axis=0)[None,:], ABS_INT_START, ABS_INT_END)[0])
            fl_ci.append(-integrate_window(scope_time_ms, np.mean(scope_corrected[ci], axis=0)[None,:], SCOPE_INT_START, SCOPE_INT_END)[0])
        else:
            abs_ci.append(np.nan); fl_ci.append(np.nan)

    ax_abs_open.plot(xd, abs_oi, 'o-', label=f'{sv}', markersize=4)
    ax_abs_closed.plot(xd, abs_ci, 'o-', label=f'{sv}', markersize=4)
    ax_fl.plot(xd, fl_oi, 'o-', label=f'{sv} open', markersize=4)
    ax_fl.plot(xd, fl_ci, 's--', label=f'{sv} closed', markersize=4, alpha=0.7)

for ax, title in [(ax_abs_open, 'Absorption OD (shutter open)'),
                   (ax_abs_closed, 'Absorption OD (shutter closed)'),
                   (ax_fl, 'Fluorescence: open vs closed')]:
    ax.set_xlabel(scan_label, fontsize=13)
    ax.set_title(title, fontsize=14)
    ax.legend(title=SECONDARY_COL, fontsize=8)
    ax.grid(True, alpha=0.3)
ax_abs_open.set_ylabel('Integrated OD [ms]', fontsize=13)
ax_abs_closed.set_ylabel('Integrated OD [ms]', fontsize=13)
ax_fl.set_ylabel('Integrated fluorescence [V*ms]', fontsize=13)
plt.tight_layout(); plt.show()"""

TIME_TRACES = """\
fig_abs, (ax_ao, ax_ac) = plt.subplots(1, 2, figsize=(14, 5))
fig_fl, (ax_fo, ax_fc) = plt.subplots(1, 2, figsize=(14, 5))
colors = [f'C{i}' for i in range(len(sec_vals))]
t_rel_abs = abs_time_ms - tYAG_MS
t_rel_fl = scope_time_ms - tYAG_MS

for ci, sv in enumerate(sec_vals):
    ao, ac, fo, fc = [], [], [], []
    for xv in scan_vals:
        om = (df[SHUTTER_COL] == True) & (df[SCAN_COL] == xv) & (df[SECONDARY_COL] == sv)
        cm = (df[SHUTTER_COL] == False) & (df[SCAN_COL] == xv) & (df[SECONDARY_COL] == sv)
        oi, cii = df.index[om].tolist(), df.index[cm].tolist()
        if oi:
            ao.append(np.mean(abs_OD[oi], axis=0))
            fo.append(np.mean(scope_corrected[oi], axis=0))
        if cii:
            ac.append(np.mean(abs_OD[cii], axis=0))
            fc.append(np.mean(scope_corrected[cii], axis=0))

    for traces, ax, t_rel in [(ao,ax_ao,t_rel_abs),(ac,ax_ac,t_rel_abs),
                               (fo,ax_fo,t_rel_fl),(fc,ax_fc,t_rel_fl)]:
        if not traces: continue
        stack = np.array(traces)
        sign = -1 if ax in (ax_fo, ax_fc) else 1
        for tr in stack:
            ax.plot(t_rel, sign*tr, color=colors[ci], alpha=0.1, linewidth=0.5)
        ax.plot(t_rel, sign*np.mean(stack, axis=0), color=colors[ci], lw=1.5, label=f'{sv}')

for ax, title in [(ax_ao,'Absorption OD (shutter open)'),(ax_ac,'Absorption OD (shutter closed)')]:
    ax.axvline(0, color='r', ls='--', alpha=0.5, label='YAG')
    ax.set_xlim(T_REL_START, T_REL_END)
    ax.set_xlabel('Time relative to YAG [ms]'); ax.set_ylabel('OD')
    ax.set_title(title); ax.legend(title=SECONDARY_COL); ax.grid(True, alpha=0.3)

for ax, title in [(ax_fo,'Fluorescence (shutter open)'),(ax_fc,'Fluorescence (shutter closed)')]:
    ax.axvline(0, color='r', ls='--', alpha=0.5, label='YAG')
    ax.set_xlim(T_REL_START, T_REL_END)
    ax.set_xlabel('Time relative to YAG [ms]'); ax.set_ylabel('-Voltage [V]')
    ax.set_title(title); ax.legend(title=SECONDARY_COL); ax.grid(True, alpha=0.3)

fig_abs.suptitle('Absorption OD time traces'); fig_abs.tight_layout()
fig_fl.suptitle('Fluorescence time traces'); fig_fl.tight_layout()
plt.show()"""

HEATMAP = """\
abs_t_rel = abs_time_ms - tYAG_MS
abs_mask = (abs_t_rel >= T_REL_START) & (abs_t_rel <= T_REL_END)
abs_t_crop = abs_t_rel[abs_mask]
scope_t_rel = scope_time_ms - tYAG_MS
scope_mask = (scope_t_rel >= T_REL_START) & (scope_t_rel <= T_REL_END)
scope_t_crop = scope_t_rel[scope_mask]

n_scan = len(scan_vals)
open_mask = df[SHUTTER_COL] == True

abs_hm, fl_hm = {}, {}
for sv in sec_vals:
    a2d = np.full((abs_mask.sum(), n_scan), np.nan)
    f2d = np.full((scope_mask.sum(), n_scan), np.nan)
    for si, xv in enumerate(scan_vals):
        sm = open_mask & (df[SCAN_COL] == xv) & (df[SECONDARY_COL] == sv)
        idxs = df.index[sm].tolist()
        if idxs:
            a2d[:, si] = np.mean(abs_OD[idxs], axis=0)[abs_mask]
            f2d[:, si] = -np.mean(scope_corrected[idxs], axis=0)[scope_mask]
    abs_hm[sv] = a2d; fl_hm[sv] = f2d

abs_vmax = max(np.nanmax(np.abs(h)) for h in abs_hm.values())
fl_vmax = max(np.nanmax(np.abs(h)) for h in fl_hm.values())
nsv = len(sec_vals)

fig_a, ax_a = plt.subplots(1, nsv, figsize=(5*nsv+2, 5), sharey=True, constrained_layout=True)
if nsv == 1: ax_a = [ax_a]
for i, sv in enumerate(sec_vals):
    pcm = ax_a[i].pcolormesh(scan_display, abs_t_crop, abs_hm[sv], shading='nearest',
                              cmap='RdBu_r', vmin=-abs_vmax, vmax=abs_vmax)
    ax_a[i].axhline(0, color='k', ls='--', lw=0.8, alpha=0.6)
    ax_a[i].set_xlabel(scan_label); ax_a[i].set_title(f'{SECONDARY_COL} = {sv}')
    if i == 0: ax_a[i].set_ylabel('Time relative to YAG [ms]')
fig_a.colorbar(pcm, ax=ax_a, shrink=0.8, pad=0.02, label='OD')
fig_a.suptitle('Absorption OD (shutter open)'); plt.show()

fig_f, ax_f = plt.subplots(1, nsv, figsize=(5*nsv+2, 5), sharey=True, constrained_layout=True)
if nsv == 1: ax_f = [ax_f]
for i, sv in enumerate(sec_vals):
    pcm = ax_f[i].pcolormesh(scan_display, scope_t_crop, fl_hm[sv], shading='nearest',
                              cmap='inferno', vmin=0, vmax=fl_vmax)
    ax_f[i].axhline(0, color='w', ls='--', lw=0.8, alpha=0.6)
    ax_f[i].set_xlabel(scan_label); ax_f[i].set_title(f'{SECONDARY_COL} = {sv}')
    if i == 0: ax_f[i].set_ylabel('Time relative to YAG [ms]')
fig_f.colorbar(pcm, ax=ax_f, shrink=0.8, pad=0.02, label='-Voltage [V]')
fig_f.suptitle('Fluorescence (shutter open)'); plt.show()"""


def build_notebook(header, config, metadata):
    cells = [
        make_cell("markdown", header),
        make_cell("code", IMPORTS),
        make_cell("code", config),
        make_cell("markdown", "### Load per-shot globals"),
        make_cell("code", LOAD_GLOBALS),
        make_cell("markdown", "### Load traces"),
        make_cell("code", LOAD_TRACES),
        make_cell("markdown", "### Baseline correction, OD & scope alignment"),
        make_cell("code", BASELINE_OD),
        make_cell("markdown", "### Spectroscopy: integrated signal vs scan variable"),
        make_cell("code", SPECTROSCOPY),
        make_cell("markdown", "### Averaged time traces"),
        make_cell("code", TIME_TRACES),
        make_cell("markdown", "### 2D heatmap: time series vs scan variable"),
        make_cell("code", HEATMAP),
        make_cell("code", ""),
    ]
    return {"nbformat": 4, "nbformat_minor": 5, "metadata": metadata, "cells": cells}


if __name__ == '__main__':
    out_dir = os.path.dirname(__file__)

    configs = [
        {
            'filename': 'Closed_cell_03_06_2026_seq02_tisa.ipynb',
            'header': '## Closed cell data \u2014 2026-03-06, Sequence 0002\nTiSa frequency scan \u00d7 V_YAG1 \u00d7 shutter interleaving.',
            'config': """\
# === CONFIGURATION ===
DATA_ROOT = r'C:\\Users\\radmo\\MIT Dropbox\\Shungo Fukaya\\Experiments\\Main_Experiment\\Closed_cell\\2026\\03\\06'
SEQ_NUM = 2
SEQ_FOLDER = os.path.join(DATA_ROOT, f'{SEQ_NUM:04d}')

SCAN_COL = 'TISA_1'
SECONDARY_COL = 'V_YAG1'
SHUTTER_COL = 'LIF_SHUTTER_OPEN'
GLOBAL_NAMES = [SCAN_COL, SECONDARY_COL, SHUTTER_COL, 'tYAG', 'tstart']

ABS_TRACE = 'Absorption3'
SCOPE_CH = 0
ABS_OFFSET_START = 0.05
ABS_OFFSET_END = 30.0
SCOPE_OFFSET_START = 0.05
SCOPE_OFFSET_END = 30.0
T_REL_START = -1.0
T_REL_END = 10.0""",
        },
        {
            'filename': 'Closed_cell_03_06_2026_seq04_tisa.ipynb',
            'header': '## Closed cell data \u2014 2026-03-06, Sequence 0004\nTiSa frequency scan \u00d7 V_YAG1 \u00d7 shutter interleaving.\nTISA_1: 31 pts 348.660925\u2013348.661425, V_YAG1: [850, 870]',
            'config': """\
# === CONFIGURATION ===
DATA_ROOT = r'C:\\Users\\radmo\\MIT Dropbox\\Shungo Fukaya\\Experiments\\Main_Experiment\\Closed_cell\\2026\\03\\06'
SEQ_NUM = 4
SEQ_FOLDER = os.path.join(DATA_ROOT, f'{SEQ_NUM:04d}')

SCAN_COL = 'TISA_1'
SECONDARY_COL = 'V_YAG1'
SHUTTER_COL = 'LIF_SHUTTER_OPEN'
GLOBAL_NAMES = [SCAN_COL, SECONDARY_COL, SHUTTER_COL, 'tYAG', 'tstart']

ABS_TRACE = 'Absorption3'
SCOPE_CH = 0
ABS_OFFSET_START = 0.05
ABS_OFFSET_END = 30.0
SCOPE_OFFSET_START = 0.05
SCOPE_OFFSET_END = 30.0
T_REL_START = -1.0
T_REL_END = 10.0""",
        },
        {
            'filename': 'Closed_cell_03_06_2026_seq03_vexlum.ipynb',
            'header': '## Closed cell data \u2014 2026-03-06, Sequence 0003\nVexlum frequency scan \u00d7 V_YAG1 \u00d7 shutter interleaving.',
            'config': """\
# === CONFIGURATION ===
DATA_ROOT = r'C:\\Users\\radmo\\MIT Dropbox\\Shungo Fukaya\\Experiments\\Main_Experiment\\Closed_cell\\2026\\03\\06'
SEQ_NUM = 3
SEQ_FOLDER = os.path.join(DATA_ROOT, f'{SEQ_NUM:04d}')

SCAN_COL = 'VEXLUM'
SECONDARY_COL = 'V_YAG1'
SHUTTER_COL = 'LIF_SHUTTER_OPEN'
GLOBAL_NAMES = [SCAN_COL, SECONDARY_COL, SHUTTER_COL, 'tYAG', 'tstart']

ABS_TRACE = 'Absorption3'
SCOPE_CH = 0
ABS_OFFSET_START = 0.05
ABS_OFFSET_END = 30.0
SCOPE_OFFSET_START = 0.05
SCOPE_OFFSET_END = 30.0
T_REL_START = -1.0
T_REL_END = 10.0""",
        },
    ]

    for cfg in configs:
        nb = build_notebook(cfg['header'], cfg['config'], meta)
        path = os.path.join(out_dir, cfg['filename'])
        with open(path, 'w') as f:
            json.dump(nb, f, indent=1)
        print(f"Wrote: {path}")
