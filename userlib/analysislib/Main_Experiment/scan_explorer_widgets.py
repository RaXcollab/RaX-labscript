"""
Explorer widget setup for scan analysis.

Displays experiment/date/sequence picker widgets. When the user clicks
"Load & Process", a ScanAnalysis object is created and automatically injected
into the notebook as ``sa``. All subsequent cells can use
``sa.spectroscopy()``, ``sa.heatmap()``, etc. without any extra import.

Usage in notebook:

    # Cell 1 — run once per kernel
    import sys; sys.path.insert(0, '..')
    %load_ext autoreload
    %autoreload 3
    from scan_explorer_widgets import setup_explorer
    setup_explorer()                      # defaults to Closed_cell
    # setup_explorer('Main_Experiment')   # or any other experiment folder

    # Cell 2+ — after clicking Load, 'sa' is available everywhere
    sa.overview()
    sa.spectroscopy(abs_int=(0.05, 6), fl_int=(2, 12))
"""

import os
import glob
import logging
import ipywidgets as widgets
from IPython.display import display, clear_output
from IPython import get_ipython
from scan_plots import ScanAnalysis

log = logging.getLogger(__name__)

# Default data root and experiment name. Override via setup_explorer() args.
DEFAULT_BASE = r'C:\Users\radmo\MIT Dropbox\Shungo Fukaya\Experiments\Main_Experiment'
DEFAULT_EXPERIMENT = 'Closed_cell'


def _get_state():
    """Return the explorer state dict, stored in IPython's user_ns so it
    survives %autoreload module reloads (module-level dicts get recreated
    on reload, causing duplicate widget handlers)."""
    ip = get_ipython()
    if ip is None:
        # Not in IPython — fall back to module-level dict
        return _MODULE_STATE
    key = '_scan_explorer_state'
    if key not in ip.user_ns:
        ip.user_ns[key] = {'sa': None, 'widgets_created': False}
        log.debug("Created new explorer state in user_ns")
    return ip.user_ns[key]

# Fallback for non-IPython use
_MODULE_STATE = {'sa': None, 'widgets_created': False}

# Style for the status HTML widget (monospace, compact)
_PRE_STYLE = 'font-family: monospace; font-size: 12px; margin: 4px 0; white-space: pre-wrap;'


def _status_html(lines):
    """Convert a list of status strings to styled HTML for the status widget."""
    text = '\n'.join(lines)
    return f'<pre style="{_PRE_STYLE}">{text}</pre>'


def _load_summary_html(sa, source='h5'):
    """Build a compact, grouped HTML summary after loading a ScanAnalysis."""
    import numpy as np
    n = len(sa.df)
    scan = sa.scan_col
    sec = sa.secondary_col
    n_scan = len(sa._scan_vals_raw)
    sec_vals = sa.sec_vals
    tYAG = sa.tYAG_ms

    # OD range
    trig = np.searchsorted(sa.abs_time_ms, tYAG)
    od_min = np.nanmin(sa.abs_OD[:, trig:])
    od_max = np.nanmax(sa.abs_OD[:, trig:])

    # Fluorescence peak
    sc_trig = np.searchsorted(sa.scope_time_ms, tYAG)
    avg_fl = np.nanmean(np.abs(sa.scope_corrected), axis=0)
    peak_idx = np.argmax(avg_fl[sc_trig:]) + sc_trig
    fl_peak = sa.scope_time_ms[peak_idx]

    # Source tag
    if source == 'cache':
        source_tag = '<span style="color: #080;">from cache</span>'
        meta = getattr(sa, '_cache_meta', {})
        extras = []
        if meta.get('downsample_scope'):
            extras.append(f'scope {meta["downsample_scope"]}x')
        tw = meta.get('time_window')
        if tw:
            extras.append(f'{tw[0]}-{tw[1]} ms window')
        if meta.get('abs_int'):
            extras.append(f'abs_int={tuple(meta["abs_int"])}')
        if meta.get('fl_int'):
            extras.append(f'fl_int={tuple(meta["fl_int"])}')
        if extras:
            source_tag += f' <span style="color: #666;">({", ".join(extras)})</span>'
    else:
        source_tag = '<span style="color: #c60;">from h5</span>'

    html = f'''<div style="font-family: monospace; font-size: 12px; line-height: 1.4;">
<b>Loaded {n} shots</b> &nbsp;|&nbsp; tYAG = {tYAG:.1f} ms &nbsp;|&nbsp; {source_tag}
<table style="margin: 2px 0; border-spacing: 8px 0;">
<tr><td style="color: #666;">Scan:</td><td><b>{scan}</b> ({n_scan} values)</td></tr>
<tr><td style="color: #666;">Secondary:</td><td><b>{sec}</b> = {sec_vals}</td></tr>
<tr><td style="color: #666;">OD range:</td><td>{od_min:.4f} to {od_max:.4f}</td></tr>
<tr><td style="color: #666;">Fluor peak:</td><td>{fl_peak:.2f} ms (tYAG + {fl_peak - tYAG:.2f} ms)</td></tr>
</table>
<span style="color: #080;">'sa' ready</span> &mdash;
<span style="color: #666;">overview() | interactive_bounds() | spectroscopy() | time_traces() | heatmap()</span>
</div>'''
    return html


def _detect_scan(folder):
    """Read first 20 h5 files, return {global_name: n_unique}."""
    import h5py  # imported here so scan_analysis's h5_lock runs first
    files = sorted(glob.glob(os.path.join(folder, '*.h5')))[:20]
    if not files:
        return {}
    with h5py.File(files[0], 'r') as f:
        keys = list(f['globals'].attrs.keys())
    vals = {k: set() for k in keys}
    for fp in files:
        with h5py.File(fp, 'r') as f:
            for k in keys:
                vals[k].add(str(f['globals'].attrs[k]))
    return {k: len(v) for k, v in vals.items()}


def setup_explorer(experiment='Closed_cell', base=None):
    """Create and display the explorer widgets.

    Parameters
    ----------
    experiment : str
        Experiment subfolder name under the base data path. This determines
        which folder tree to browse (e.g. 'Closed_cell', 'Main_Experiment').
        Also used in plot titles and printout.
    base : str, optional
        Root data path. Defaults to the Dropbox experiment folder.
        Full path to sequence data is: base/experiment/YYYY/MM/DD/SSSS/

    After clicking "Load & Process", the variable ``sa`` is injected into the
    notebook namespace. All cells can use ``sa.spectroscopy()``, etc. directly.

    Idempotent — re-running the cell won't create duplicate widgets or handlers.
    """
    _state = _get_state()
    log.debug("setup_explorer called, widgets_created=%s, id(_state)=%s",
              _state.get('widgets_created'), id(_state))

    _state['experiment'] = experiment
    _state['base'] = base or DEFAULT_BASE

    # Widgets (created once, reused on re-run)
    if not _state['widgets_created']:
        log.debug("Creating new widgets + handlers")
        _dw = {'description_width': '100px'}
        _state['w_exp'] = widgets.Text(
            value=experiment, description='Experiment:', style=_dw)
        _state['w_date'] = widgets.Text(
            value='2026/03/06', description='Date (Y/M/D):', style=_dw)
        _state['w_seq'] = widgets.IntText(
            value=2, description='Sequence #:', style=_dw)
        _state['w_scan'] = widgets.Dropdown(
            options=['(auto-detect)'], description='Scan col:', style=_dw)
        _state['w_sec'] = widgets.Dropdown(
            options=['(auto-detect)'], description='Secondary:', style=_dw)
        _state['w_detect'] = widgets.Button(
            description='Detect Scan', button_style='info')
        _state['w_force_reimport'] = widgets.Checkbox(
            value=False, description='Force reimport',
            style={'description_width': 'auto'},
            layout=widgets.Layout(width='160px'))
        _state['w_load'] = widgets.Button(
            description='Load & Process', button_style='primary')
        # HTML widget instead of Output widget to avoid VSCode duplicate
        # rendering bug (microsoft/vscode-jupyter#11540)
        _state['w_out'] = widgets.HTML(value='')

        # Cache controls
        cache_dir = os.path.join(_state['base'], experiment, '.scan_cache')
        _state['w_cache_dir'] = widgets.Text(
            value=cache_dir, description='Cache folder:',
            style={'description_width': '100px'},
            layout=widgets.Layout(width='600px'))
        _state['w_auto_cache'] = widgets.Checkbox(
            value=True, description='Auto-save on import',
            style={'description_width': 'auto'},
            layout=widgets.Layout(width='180px'))
        _state['w_downsample'] = widgets.Dropdown(
            options=[('Full', None), ('5x', 5), ('10x', 10), ('20x', 20), ('100x', 100)],
            value=10, description='Scope downsample:',
            style={'description_width': 'auto'},
            layout=widgets.Layout(width='200px'))
        _state['w_exclude_raw'] = widgets.Checkbox(
            value=True, description='Skip raw abs',
            style={'description_width': 'auto'},
            layout=widgets.Layout(width='140px'))
        _state['w_time_end'] = widgets.FloatText(
            value=50.0, description='Time end (ms):',
            style={'description_width': 'auto'},
            layout=widgets.Layout(width='170px'), step=10)
        _state['w_save_cache'] = widgets.Button(
            description='Save Cache', button_style='success',
            layout=widgets.Layout(width='120px'))
        _state['w_cache_info'] = widgets.HTML(value='')

        # Attach handlers ONCE
        _state['w_detect'].on_click(_on_detect)
        _state['w_load'].on_click(_on_load)
        _state['w_save_cache'].on_click(_on_save_cache)
        _state['widgets_created'] = True
    else:
        log.debug("Reusing existing widgets (skipping handler registration)")
        # Update experiment name if setup_explorer is called again with different args
        _state['w_exp'].value = experiment

    w = _state

    # Single container widget — prevents multiple views of w_out
    # which causes duplicated print output on re-run.
    if 'container' not in w:
        w['container'] = widgets.VBox([
            widgets.HBox([w['w_exp'], w['w_date'], w['w_seq'], w['w_detect']]),
            widgets.HBox([w['w_scan'], w['w_sec'], w['w_force_reimport'],
                          w['w_load']]),
            w['w_cache_dir'],
            widgets.HBox([w['w_auto_cache'], w['w_downsample'],
                          w['w_time_end'], w['w_exclude_raw'],
                          w['w_save_cache'], w['w_cache_info']]),
            w['w_out'],
        ])
    clear_output(wait=True)
    display(w['container'])

    # Auto-detect on first setup
    _on_detect()

    return _state


def _get_folder():
    """Build the sequence folder path from current widget values."""
    w = _get_state()
    return os.path.join(w['base'], w['w_exp'].value, w['w_date'].value, f"{w['w_seq'].value:04d}")


def _get_cache_path():
    """Build the cache file path from current widget values."""
    w = _get_state()
    cache_dir = w['w_cache_dir'].value
    date_str = w['w_date'].value.replace('/', '-')
    seq_num = w['w_seq'].value
    return os.path.join(cache_dir, f'{date_str}_{seq_num:04d}.npz')


def _get_cache_options(w):
    """Parse downsample, exclude, and time_window settings from widgets."""
    ds_val = w['w_downsample'].value
    downsample = {'scope': ds_val} if ds_val else None
    exclude = ['_abs_raw'] if w['w_exclude_raw'].value else None
    t_end = w['w_time_end'].value
    time_window = (0, t_end) if t_end and t_end > 0 else None
    return downsample, exclude, time_window


def _update_cache_info(w):
    """Refresh the cache info HTML widget."""
    try:
        cache_path = _get_cache_path()
        folder = _get_folder()
        status = ScanAnalysis.cache_status(cache_path, seq_folder=folder)
    except Exception:
        w['w_cache_info'].value = ''
        return

    if not status['exists']:
        w['w_cache_info'].value = (
            '<span style="font-size: 11px; color: #999;">No cache</span>')
        return

    meta = status.get('meta') or {}
    size = status['size_mb']
    parts = [f'{size:.1f} MB']
    if meta.get('downsample_scope'):
        parts.append(f'scope {meta["downsample_scope"]}x')
    tw = meta.get('time_window')
    if tw:
        parts.append(f'{tw[0]}-{tw[1]} ms')
    if status['valid']:
        color = '#080'
        parts.append('valid')
    else:
        color = '#c60'
        parts.append('stale')
    text = ' | '.join(parts)
    w['w_cache_info'].value = (
        f'<span style="font-size: 11px; color: {color};">{text}</span>')


def _inject_sa(new_sa, w, source='h5'):
    """Inject ScanAnalysis into notebook namespace and update status display."""
    ip = get_ipython()
    if ip:
        ip.user_ns['sa'] = new_sa
    w['sa'] = new_sa
    w['w_out'].value = _load_summary_html(new_sa, source=source)
    _update_cache_info(w)


def _on_detect(b=None):
    log.debug("_on_detect fired (b=%s)", b)
    w = _get_state()
    folder = _get_folder()
    if not os.path.isdir(folder):
        w['w_out'].value = _status_html([f'Folder not found: {folder}'])
        return

    counts = _detect_scan(folder)
    skip = {'LIF_SHUTTER_OPEN', 'tend', 'tstart', 'tYAG', 'DOUBLE_YAG',
            'YAG_DELAY', 'ENH_DURATION', 'ENH_START'}
    scanned = sorted([k for k, n in counts.items() if n > 1 and k not in skip])
    fixed = sorted([k for k, n in counts.items() if n <= 1 and k not in skip])

    by_count = sorted([(counts[k], k) for k in scanned], reverse=True)
    scan_guess = by_count[0][1] if by_count else ''
    sec_candidates = [k for k in scanned if k != scan_guess]
    sec_guess = sec_candidates[0] if sec_candidates else ''

    w['w_scan'].options = scanned or ['(none)']
    w['w_scan'].value = scan_guess
    w['w_sec'].options = scanned + fixed
    w['w_sec'].value = sec_guess if sec_guess else (fixed[0] if fixed else scanned[0] if scanned else '')

    lines = [f'Detected in ...{os.path.basename(folder)}:']
    for k in scanned:
        lines.append(f'  {k}: {counts[k]} unique (scanned)')
    w['w_out'].value = _status_html(lines)
    _update_cache_info(w)


def _on_load(b=None):
    """Load button callback. Tries cache first, falls back to h5 import.

    After loading, injects ``sa`` into the notebook namespace. If auto-save
    is enabled and data was loaded from h5, saves a cache file automatically.
    """
    w = _get_state()
    folder = _get_folder()
    cache_path = _get_cache_path()
    force = w['w_force_reimport'].value

    # Try cache first (unless force reimport)
    if not force:
        try:
            status = ScanAnalysis.cache_status(cache_path, seq_folder=folder)
            if status['exists'] and status['valid']:
                w['w_out'].value = _status_html(['Loading from cache...'])
                import io, contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    new_sa = ScanAnalysis.from_cache(cache_path,
                                                     seq_folder=folder)
                _inject_sa(new_sa, w, source='cache')
                return
        except Exception as e:
            log.warning("Cache load failed, falling back to h5: %s", e)

    # Import from h5 files
    w['w_out'].value = _status_html([f'Loading from h5: {folder}...'])
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        new_sa = ScanAnalysis(folder, scan_col=w['w_scan'].value,
                              secondary_col=w['w_sec'].value)

    # Auto-save cache after successful h5 import
    if w['w_auto_cache'].value:
        try:
            downsample, exclude, time_window = _get_cache_options(w)
            with contextlib.redirect_stdout(io.StringIO()):
                new_sa.save_cache(path=cache_path, downsample=downsample,
                                  exclude=exclude, time_window=time_window)
        except Exception as e:
            log.warning("Auto-save cache failed: %s", e)

    _inject_sa(new_sa, w, source='h5')


def _on_save_cache(b=None):
    """Manual Save Cache button handler."""
    w = _get_state()
    sa = w.get('sa')
    if sa is None:
        w['w_cache_info'].value = (
            '<span style="font-size: 11px; color: #c00;">No data loaded</span>')
        return
    cache_path = _get_cache_path()
    downsample, exclude, time_window = _get_cache_options(w)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sa.save_cache(path=cache_path, downsample=downsample, exclude=exclude,
                      time_window=time_window)
    _update_cache_info(w)
