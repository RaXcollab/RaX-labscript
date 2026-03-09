"""
scan_analysis.py
Scan-level analysis utilities for labscript experiments.

Sits above Abs_data.py and NI_SCOPE.py — handles per-shot globals extraction,
grouping, background subtraction, and signal integration across scanned parameters.

All functions take explicit parameters; nothing is hardcoded to a specific scan type.
"""

import os
import numpy as np
import pandas as pd
import labscript_utils.h5_lock  # noqa: F401 — must precede h5py
import h5py
from concurrent.futures import ThreadPoolExecutor
from filtering import process_trace
from NI_SCOPE import _resolve_fs_hz


# ---------------------------------------------------------------------------
# 1. Per-shot globals extraction
# ---------------------------------------------------------------------------

def _read_shot_globals(args):
    """Worker: extract expanded per-shot globals directly from h5.

    Labscript stores globals as string expressions (e.g. 'np.linspace(...)') plus
    expansion type ('outer'). For 'outer' scans, the per-shot value is determined by
    `run number` indexing into the outer product of all expanded arrays.
    We use lyse.Run (imported in main thread) to handle the expansion logic.
    """
    h5_path, global_names, lyse_mod = args
    row = {'h5_path': h5_path}
    try:
        run = lyse_mod.Run(h5_path)
        g = run.get_globals()
        names = global_names if global_names is not None else list(g.keys())
        for name in names:
            row[name] = g.get(name, np.nan)
        with h5py.File(h5_path, 'r') as f:
            row['run_number'] = int(f.attrs.get('run number', -1))
        row['_valid'] = True
    except Exception as e:
        row['_valid'] = False
        print(f"Warning: globals extraction failed for {os.path.basename(h5_path)}: {e}")
    return row


def load_scan_globals(seq_folder, global_names=None):
    """Load expanded per-shot globals from all h5 files in a sequence folder.

    Parameters
    ----------
    seq_folder : str
        Path to the sequence folder (e.g. `.../0006/`).
    global_names : list of str or None
        Names of globals to extract. If None (default), loads ALL globals
        from the h5 files — every parameter the sequence used is available
        in the returned DataFrame.

    Returns
    -------
    pd.DataFrame
        Columns: h5_path, run_number, + one column per global.
        Sorted by run_number. Invalid shots are excluded.
    """
    import lyse  # must import in main thread (signal handler)

    files = sorted([f for f in os.listdir(seq_folder) if f.endswith('.h5')])
    if not files:
        raise FileNotFoundError(f"No h5 files in {seq_folder}")

    # Sequential — lyse.Run uses h5_lock which requires main-thread signal handling
    rows = []
    for f in files:
        row = _read_shot_globals((os.path.join(seq_folder, f), global_names, lyse))
        rows.append(row)

    df = pd.DataFrame(rows)
    df = df[df['_valid']].drop(columns=['_valid']).reset_index(drop=True)
    df = df.sort_values('run_number').reset_index(drop=True)

    # Report what was loaded
    loaded_globals = [c for c in df.columns if c not in ('h5_path', 'run_number')]
    print(f"load_scan_globals: {len(df)}/{len(files)} shots loaded from {os.path.basename(seq_folder)}")
    for name in loaded_globals:
        unique = df[name].nunique()
        print(f"  {name}: {unique} unique values")
    return df


# ---------------------------------------------------------------------------
# 2. Trace loading (absorption-style structured traces)
# ---------------------------------------------------------------------------

def _read_one_trace(args):
    """Worker: read a single named trace from one h5 file."""
    h5_path, trace_name, get_time = args
    result = {'values': None, 'time': None}
    try:
        with h5py.File(h5_path, 'r') as f:
            path = f'data/traces/{trace_name}'
            if path not in f:
                return result
            dset = f[path]
            result['values'] = dset['values'][:]
            if get_time:
                t_col = dset.dtype.names[0]
                result['time'] = dset[t_col][:]
    except Exception as e:
        print(f"Warning: trace read failed for {os.path.basename(h5_path)}: {e}")
    return result


def load_scan_traces(seq_folder, trace_name, df=None):
    """Load a named absorption-style trace from all shots in a sequence.

    Parameters
    ----------
    seq_folder : str
        Sequence folder path.
    trace_name : str
        Trace name in h5 (e.g. 'Absorption3').
    df : pd.DataFrame, optional
        If provided, only loads files listed in df['h5_path'] and aligns rows.

    Returns
    -------
    dict with keys:
        'time'       : 1D array (nsamples,) — shared time axis
        'data'       : 2D array (nshots, nsamples) — trace values
        'valid_mask' : 1D bool array (nshots,) — True where data was loaded
    """
    if df is not None:
        h5_paths = df['h5_path'].tolist()
    else:
        files = sorted([f for f in os.listdir(seq_folder) if f.endswith('.h5')])
        h5_paths = [os.path.join(seq_folder, f) for f in files]

    tasks = [(p, trace_name, (i == 0)) for i, p in enumerate(h5_paths)]

    with ThreadPoolExecutor() as pool:
        results = list(pool.map(_read_one_trace, tasks))

    # Extract shared time from first valid result
    shared_time = None
    for r in results:
        if r['time'] is not None:
            shared_time = r['time']
            break

    if shared_time is None:
        raise RuntimeError(f"Could not extract time axis for trace '{trace_name}'")

    n = len(h5_paths)
    nsamp = shared_time.shape[0]
    data = np.full((n, nsamp), np.nan)
    valid_mask = np.zeros(n, dtype=bool)

    for i, r in enumerate(results):
        if r['values'] is not None and r['values'].shape == shared_time.shape:
            data[i] = r['values']
            valid_mask[i] = True

    n_valid = valid_mask.sum()
    n_dropped = n - n_valid
    if n_dropped:
        print(f"load_scan_traces('{trace_name}'): {n_dropped}/{n} shots dropped (missing or shape mismatch)")
    print(f"load_scan_traces('{trace_name}'): {n_valid} valid shots, {nsamp} samples each")

    return {'time': shared_time, 'data': data, 'valid_mask': valid_mask}


# ---------------------------------------------------------------------------
# 3. NI_SCOPE loading (raw 2D array traces)
# ---------------------------------------------------------------------------

def _read_one_scope(args):
    """Worker: read NI_SCOPE channel from one h5 file."""
    h5_path, ch = args
    try:
        with h5py.File(h5_path, 'r') as f:
            for key in ['data/traces/NI_SCOPE', 'data/traces/ni_scope']:
                if key in f and isinstance(f[key], h5py.Dataset):
                    arr = f[key][()]
                    if arr.ndim == 2 and arr.shape[0] >= ch + 1:
                        return arr[ch]
    except Exception as e:
        print(f"Warning: scope read failed for {os.path.basename(h5_path)}: {e}")
    return None


def load_scan_scope(seq_folder, ch=0, fs_hz=None, df=None):
    """Load NI_SCOPE channel data from all shots in a sequence.

    Parameters
    ----------
    seq_folder : str
        Sequence folder path.
    ch : int
        Channel index (0 or 1).
    fs_hz : float or None
        Sample rate override. If None, auto-detected from h5 attrs.
    df : pd.DataFrame, optional
        If provided, only loads files listed in df['h5_path'].

    Returns
    -------
    dict with keys:
        'time_ms'    : 1D array — time axis in ms
        'data'       : 2D array (nshots, nsamples)
        'valid_mask' : 1D bool array
    """
    if df is not None:
        h5_paths = df['h5_path'].tolist()
    else:
        files = sorted([f for f in os.listdir(seq_folder) if f.endswith('.h5')])
        h5_paths = [os.path.join(seq_folder, f) for f in files]

    # Resolve sample rate from first file
    resolved_fs = _resolve_fs_hz(h5_paths[0], fs_hz)

    tasks = [(p, ch) for p in h5_paths]
    with ThreadPoolExecutor() as pool:
        results = list(pool.map(_read_one_scope, tasks))

    # Find reference length from first valid result
    ref_len = None
    for r in results:
        if r is not None:
            ref_len = r.shape[0]
            break
    if ref_len is None:
        raise RuntimeError("No valid NI_SCOPE data found")

    n = len(h5_paths)
    data = np.full((n, ref_len), np.nan)
    valid_mask = np.zeros(n, dtype=bool)

    for i, r in enumerate(results):
        if r is not None and r.shape[0] == ref_len:
            data[i] = r
            valid_mask[i] = True

    time_ms = np.arange(ref_len) / resolved_fs * 1000.0

    n_valid = valid_mask.sum()
    print(f"load_scan_scope(ch={ch}): {n_valid}/{n} valid shots, {ref_len} samples @ {resolved_fs/1e6:.1f} MHz")

    return {'time_ms': time_ms, 'data': data, 'valid_mask': valid_mask}


# ---------------------------------------------------------------------------
# 4. Grouping and background subtraction
# ---------------------------------------------------------------------------

def group_and_subtract(df, data_2d, shutter_col, group_cols):
    """Group shots by scan parameters and subtract shutter-closed background.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns for `shutter_col` (bool) and each of `group_cols`.
    data_2d : 2D array (nshots, nsamples)
        Trace data aligned with df rows.
    shutter_col : str
        Column name for the shutter boolean (True = signal, False = background).
    group_cols : list of str
        Columns to group by (e.g. ['TISA_1', 'V_YAG1']).

    Returns
    -------
    dict keyed by group tuple, each value is a dict:
        'subtracted'      : 1D array — mean(signal) - mean(background)
        'signal_mean'     : 1D array
        'background_mean' : 1D array
        'signal_std'      : 1D array
        'n_signal'        : int
        'n_background'    : int
    """
    results = {}
    grouped = df.groupby(group_cols)

    for group_key, group_df in grouped:
        if not isinstance(group_key, tuple):
            group_key = (group_key,)

        sig_mask = group_df[shutter_col].astype(bool).values
        bg_mask = ~sig_mask
        idx = group_df.index.values

        sig_data = data_2d[idx[sig_mask]]
        bg_data = data_2d[idx[bg_mask]]

        sig_mean = np.nanmean(sig_data, axis=0) if len(sig_data) > 0 else np.zeros(data_2d.shape[1])
        bg_mean = np.nanmean(bg_data, axis=0) if len(bg_data) > 0 else np.zeros(data_2d.shape[1])
        sig_std = np.nanstd(sig_data, axis=0) if len(sig_data) > 1 else np.zeros(data_2d.shape[1])

        results[group_key] = {
            'subtracted': sig_mean - bg_mean,
            'signal_mean': sig_mean,
            'background_mean': bg_mean,
            'signal_std': sig_std,
            'n_signal': len(sig_data),
            'n_background': len(bg_data),
        }

    print(f"group_and_subtract: {len(results)} groups, "
          f"shutter_col='{shutter_col}', group_cols={group_cols}")
    return results


# ---------------------------------------------------------------------------
# 5. Signal integration
# ---------------------------------------------------------------------------

def integrate_window(time_array, traces_2d, t_start, t_end):
    """Integrate each trace row between t_start and t_end.

    Parameters
    ----------
    time_array : 1D array
        Time axis (ms or seconds — just be consistent).
    traces_2d : 2D array (ntraces, nsamples)
        Each row is a trace to integrate.
    t_start, t_end : float
        Integration bounds in same units as time_array.

    Returns
    -------
    1D array (ntraces,) — integrated values (trapezoidal rule).
    """
    idx0 = np.searchsorted(time_array, t_start)
    idx1 = np.searchsorted(time_array, t_end)
    if idx1 <= idx0:
        return np.zeros(traces_2d.shape[0])

    dt = np.median(np.diff(time_array[idx0:idx1]))
    segment = traces_2d[:, idx0:idx1]
    return np.trapz(segment, dx=dt, axis=1)


# ---------------------------------------------------------------------------
# 6. Batch baseline correction
# ---------------------------------------------------------------------------

def baseline_correct_batch(time_ms, traces_2d, tYAG_ms, **kwargs):
    """Apply process_trace() baseline correction to each row.

    Parameters
    ----------
    time_ms : 1D array
        Time axis in ms.
    traces_2d : 2D array (nshots, nsamples)
        Raw traces.
    tYAG_ms : float
        YAG trigger time in ms.
    **kwargs
        Passed to filtering.process_trace() (margin_ms, tail_ms, etc.)

    Returns
    -------
    2D array — corrected traces (same shape as input).
    """
    corrected = np.empty_like(traces_2d)
    for i in range(traces_2d.shape[0]):
        if np.all(np.isnan(traces_2d[i])):
            corrected[i] = traces_2d[i]
        else:
            corrected[i] = process_trace(time_ms, traces_2d[i], tYAG_ms, **kwargs)
    return corrected
