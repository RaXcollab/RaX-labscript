# Post-shot analysis for the Open_cell2 sequence.
# Layout: DC absorption (top left), FM absorption (bottom left),
# digital trigger signals (top right), EMCCD image (bottom right).

import lyse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.transforms as transforms
from filtering import process_trace

# --- Plot constants ---
XLIM_MS_ABS = 100    # ms, absorption subplots
XLIM_MS_TRIG = 100   # ms, trigger subplot (covers the 20 ms EMCCD trigger)
CMAP_VMIN, CMAP_VMAX = 1568, 1700   # EMCCD display range — adjust to LIF probe power
PHOTON_COUNT_THRESHOLD = 1690       # 1810 for 1x1 binning

# --- Sequence timing constants (mirror Open_cell2.py) ---
YAG_PULSE = 0.5e-3    # s, YAG1_line pulse width
EMCCD_DELAY = 0.1e-3  # s, camera_trig delay after tYAG
EMCCD_TRIG = 20e-3    # s, camera_trig pulse width

# --- Annotation helper ---
def _annotate_ax(ax, tYAG_1, enh_start_ms, enh_end_ms):
    """Add a YAG dotted line with text label + ENH window to an axis."""
    trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
    ax.axvline(x=tYAG_1 * 1000, color='r', linestyle=':', linewidth=1.2)
    ax.text(tYAG_1 * 1000, 0.96, ' YAG1', transform=trans, color='r', fontsize=9, va='top', ha='left')
    ax.axvspan(enh_start_ms, enh_end_ms, color='yellow', alpha=0.3)

# --- Camera failure detection helper ---
CAMERA_ORIENTATION = 'camera'
CAMERA_LABEL = 'fluorescence'
CAMERA_FRAMETYPE = 'frame'

def _check_camera_failed(run, orientation):
    """Detect whether the camera image group indicates a failed shot.

    Per docs/shot-h5-layout.md, there are two distinct failure signatures:
      1. Trigger never fired: `post_experiment` raises before the h5-write
         block, so `/images/{orientation}` is ABSENT entirely and so is the
         `failed_shot` attr (absent, NOT False).
      2. Partial acquisition: the group exists but `failed_shot=True` was
         written because an exposure failed mid-shot.
    Both must be treated as a failed shot -- testing the flag alone misses
    case 1 (`in`/`.get()` on a missing group looks like "not failed").

    Returns
    -------
    (failed, reason) : (bool, str)
    """
    try:
        attrs = run.get_image_attributes(orientation)
    except Exception:
        return True, 'no image group (camera trigger likely never fired)'
    if attrs.get('failed_shot', False):
        return True, 'failed_shot=True (camera failed mid-shot)'
    return False, ''

# --- Lyse boilerplate ---
if lyse.utils.worker.spinning_top:
    h5_path = lyse.path
else:
    df = lyse.data()
    h5_path = df.filepath.iloc[-1]

run = lyse.Run(h5_path)

# --- Detect failed camera shots early, save the flag for multishot filtering ---
camera_failed, camera_fail_reason = _check_camera_failed(run, CAMERA_ORIENTATION)
run.save_result('failed_shot', camera_failed)
if camera_failed:
    print(f"Warning: camera shot flagged as failed in {h5_path} ({camera_fail_reason}); "
          f"skipping image analysis, continuing with trace analysis.")

# --- Extract traces (graceful handling for missing traces) ---
# Traces are independent of the camera trigger, so process them regardless
# of camera_failed -- this is cheap and still useful for diagnosing a shot
# where only the camera failed.
TRACE_NAMES = ['Absorption0', 'Absorption1', 'Absorption2', 'Absorption3']
trace_data = {}
for name in TRACE_NAMES:
    try:
        trace_data[name] = run.get_trace(name)
    except Exception:
        print(f"Warning: trace '{name}' not found in {h5_path}")

# --- Extract EMCCD image (skipped entirely for a flagged-failed shot) ---
image_data = None
image_unavailable_reason = camera_fail_reason
if not camera_failed:
    try:
        image_data = run.get_image(CAMERA_ORIENTATION, CAMERA_LABEL, CAMERA_FRAMETYPE)
        if image_data is None or image_data.size == 0:
            image_unavailable_reason = 'image dataset is empty'
            image_data = None
    except Exception:
        image_unavailable_reason = f"'{CAMERA_ORIENTATION}/{CAMERA_LABEL}/{CAMERA_FRAMETYPE}' not found"
    if image_data is None:
        print(f"Warning: {image_unavailable_reason} in {h5_path}")

# --- Globals ---
global_dict = run.get_globals()
tYAG_1 = float(global_dict['tYAG_1'])
tYAG = float(global_dict.get('tYAG', tYAG_1))  # sequence times the EMCCD trigger off tYAG
ENH_START = float(global_dict['ENH_START'])
ENH_DURATION = float(global_dict['ENH_DURATION'])
ENH_SHUTTER_DELAY = float(global_dict['ENH_SHUTTER_DELAY'])
tstart = float(global_dict['tstart']) if 'tstart' in global_dict else None
tend = float(global_dict['tend']) if 'tend' in global_dict else None

SCAN_TISA_1 = bool(global_dict.get('SCAN_TISA_1', False))
SCAN_TISA_2 = bool(global_dict.get('SCAN_TISA_2', False))
SCAN_VEXLUM = bool(global_dict.get('SCAN_VEXLUM', False))

if SCAN_TISA_1 or SCAN_TISA_2 or SCAN_VEXLUM:
    freq_ramp = float(global_dict['freq_ramp'])
    run.save_result('freq_ramp_value', freq_ramp)

# Pre-compute ENH window in ms (matches trigger timing)
enh_start_ms = (ENH_SHUTTER_DELAY + ENH_START) * 1000
enh_end_ms = (ENH_SHUTTER_DELAY + ENH_START + ENH_DURATION) * 1000
ann = lambda ax: _annotate_ax(ax, tYAG_1, enh_start_ms, enh_end_ms)

# --- Figure setup ---
fig = plt.figure(figsize=(12, 8))
gs = gridspec.GridSpec(2, 2, width_ratios=[0.9, 1.0])

# --- Subplot 1 (top left): Absorption DC (raw) ---
ax1 = fig.add_subplot(gs[0, 0])
if 'Absorption0' in trace_data:
    times_dc = trace_data['Absorption0'][0].flatten()
    values_dc = trace_data['Absorption0'][1].flatten()
    ax1.plot(times_dc * 1000, values_dc, 'b')

ax1.set_xlim([0, XLIM_MS_ABS])
ax1.set_xlabel('Time [ms]', fontsize=12)
ax1.set_ylabel('Value', fontsize=12)
ax1.set_title('Absorption_DC', fontsize=14)
ax1.grid(True)
ann(ax1)

# --- Subplot 2 (bottom left): Absorption FM (drift-corrected) ---
ax2 = fig.add_subplot(gs[1, 0])
if 'Absorption1' in trace_data and 'Absorption2' in trace_data:
    times_1 = trace_data['Absorption1'][0].flatten()
    values_1 = trace_data['Absorption1'][1].flatten()
    times_2 = trace_data['Absorption2'][0].flatten()
    values_2 = trace_data['Absorption2'][1].flatten()

    values_1_corrected = process_trace(times_1 * 1000, values_1, tYAG_ms=tYAG_1 * 1000)
    values_2_corrected = process_trace(times_2 * 1000, values_2, tYAG_ms=tYAG_1 * 1000)

    ax2.plot(times_1 * 1000, values_1_corrected, 'b', label='Absorption1')
    ax2.plot(times_2 * 1000, values_2_corrected, 'g', label='Absorption2')

    # Auto-tighten ylim if both traces fit within [-0.5, 0.5]
    vis1 = values_1_corrected[(times_1 * 1000 >= 0) & (times_1 * 1000 <= XLIM_MS_ABS)]
    vis2 = values_2_corrected[(times_2 * 1000 >= 0) & (times_2 * 1000 <= XLIM_MS_ABS)]
    if vis1.size and vis2.size:
        if min(np.nanmin(vis1), np.nanmin(vis2)) >= -0.5 and max(np.nanmax(vis1), np.nanmax(vis2)) <= 0.5:
            ax2.set_ylim([-0.3, 0.3])

ax2.set_xlim([0, XLIM_MS_ABS])
ax2.set_xlabel('Time [ms]', fontsize=12)
ax2.set_ylabel('Offset Value', fontsize=12)
ax2.set_title('Absorption_FM', fontsize=14)
ax2.grid(True)
ax2.legend(loc='upper right')
ann(ax2)

# --- Subplot 3 (top right): Digital trigger signals ---
inner_gs = gridspec.GridSpecFromSubplotSpec(2, 1, subplot_spec=gs[0, 1], hspace=0)
ax3_top = fig.add_subplot(inner_gs[0])
ax3_bot = fig.add_subplot(inner_gs[1], sharex=ax3_top)

if tstart is not None and tend is not None:
    tend_ms = (tend - tstart) * 1000
    t_ms = np.linspace(0, tend_ms, 10000)

    def _step(t, t0_s, duration_s):
        sig = np.zeros_like(t)
        lo = (t0_s - tstart) * 1000
        hi = lo + duration_s * 1000
        sig[(t >= lo) & (t < hi)] = 1.0
        return sig

    yag1 = _step(t_ms, tYAG_1, YAG_PULSE)
    enh = _step(t_ms, ENH_SHUTTER_DELAY + ENH_START, ENH_DURATION)
    emccd = _step(t_ms, tYAG + EMCCD_DELAY, EMCCD_TRIG)

    ax3_top.step(t_ms, yag1, 'b-', where='post', label='YAG1')
    ax3_bot.step(t_ms, enh, 'g-', where='post', label='enhancement')
    ax3_bot.step(t_ms, emccd, 'm-', where='post', label='EMCCD trig')

    for ax in (ax3_top, ax3_bot):
        ax.set_yticks([0, 1])
        ax.set_ylim([-0.15, 1.3])
        ax.set_xlim([0, XLIM_MS_TRIG])
        ax.legend(loc='upper right', fontsize=9)
        ax.grid(True)

    plt.setp(ax3_top.get_xticklabels(), visible=False)
    ax3_top.set_title(f"Trigger inputs (tend={tend_ms:.1f} ms)", fontsize=11)
    ax3_bot.set_xlabel('Time [ms]', fontsize=11)
else:
    ax3_top.set_title("Trigger inputs (tstart/tend not available)", fontsize=11)
    ax3_top.axis('off')
    ax3_bot.axis('off')

# --- Subplot 4 (bottom right): EMCCD fluorescence image ---
ax4 = fig.add_subplot(gs[1, 1])
if image_data is not None:
    ny, nx = image_data.shape
    ax4.imshow(image_data, extent=[0, nx, 0, ny], cmap='magma',
               vmin=CMAP_VMIN, vmax=CMAP_VMAX)
else:
    placeholder = 'EMCCD image\nnot available'
    if image_unavailable_reason:
        placeholder += f'\n({image_unavailable_reason})'
    ax4.text(0.5, 0.5, placeholder,
             transform=ax4.transAxes, ha='center', va='center', fontsize=12)
ax4.set_title('EMCCD Fluorescence', fontsize=14)
ax4.set_xlabel('x', fontsize=12)
ax4.set_ylabel('y', fontsize=12)

# --- Save results ---
if 'Absorption1' in trace_data:
    values_fm = trace_data['Absorption1'][1].flatten()
    run.save_result('BaF_abs integrated', values_fm.mean())
    run.save_result('BaF_abs integrated err', values_fm.std() / np.sqrt(len(values_fm)))

if image_data is not None:
    pixel_sum = np.mean(image_data > PHOTON_COUNT_THRESHOLD)
    run.save_result('pixel_sum', pixel_sum)

plt.tight_layout()
