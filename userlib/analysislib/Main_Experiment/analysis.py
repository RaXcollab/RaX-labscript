import lyse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.transforms as transforms
import h5py
import labscript_utils.h5_lock  # noqa: F401 — enables safe concurrent HDF5 access
import labscript_utils.properties
from filtering import process_trace

# --- Plot constants ---
XLIM_MS_ABS = 100   # ms, absorption subplots
XLIM_MS_LIF = 100   # ms, NI_SCOPE subplot

# --- Annotation helper ---
def _annotate_ax(ax, tYAG_1, tYAG_2, double_yag, enh_start_ms, enh_end_ms):
    """Add YAG dotted lines with text labels + ENH window to an axis."""
    trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
    ax.axvline(x=tYAG_1 * 1000, color='r', linestyle=':', linewidth=1.2)
    ax.text(tYAG_1 * 1000, 0.96, ' YAG1', transform=trans, color='r', fontsize=9, va='top', ha='left')
    if double_yag:
        ax.axvline(x=tYAG_2 * 1000, color='darkred', linestyle=':', linewidth=1.2)
        ax.text(tYAG_2 * 1000, 0.96, ' YAG2', transform=trans, color='darkred', fontsize=9, va='top', ha='left')
    ax.axvspan(enh_start_ms, enh_end_ms, color='yellow', alpha=0.3)

# --- Lyse boilerplate ---
if lyse.utils.worker.spinning_top:
    h5_path = lyse.path
else:
    df = lyse.data()
    h5_path = df.filepath.iloc[-1]

run = lyse.Run(h5_path)

# --- Extract traces (graceful handling for missing traces) ---
TRACE_NAMES = ['Absorption0', 'Absorption1', 'Absorption2', 'Absorption3']
trace_data = {}
for name in TRACE_NAMES:
    try:
        trace_data[name] = run.get_trace(name)
    except Exception:
        print(f"Warning: trace '{name}' not found in {h5_path}")

# --- Globals ---
global_dict = run.get_globals()
tYAG_1 = float(global_dict['tYAG_1'])
tYAG_2 = float(global_dict['tYAG_2'])
ENH_START = float(global_dict['ENH_START'])
ENH_DURATION = float(global_dict['ENH_DURATION'])
ENH_SHUTTER_DELAY = float(global_dict['ENH_SHUTTER_DELAY'])
tstart = float(global_dict['tstart']) if 'tstart' in global_dict else None
tend = float(global_dict['tend']) if 'tend' in global_dict else None
DOUBLE_YAG = bool(global_dict.get('DOUBLE_YAG', False))
YAG_DELAY = float(global_dict.get('YAG_DELAY', 0))
LIF_SHUTTER_OPEN = bool(global_dict.get('LIF_SHUTTER_OPEN', True))

SCAN_TISA_1 = bool(global_dict.get('SCAN_TISA_1', False))
SCAN_TISA_2 = bool(global_dict.get('SCAN_TISA_2', False))
SCAN_VEXLUM = bool(global_dict.get('SCAN_VEXLUM', False))

if SCAN_TISA_1 or SCAN_TISA_2 or SCAN_VEXLUM:
    freq_ramp = float(global_dict['freq_ramp'])
    run.save_result('freq_ramp_value', freq_ramp)



# Pre-compute ENH window in ms (matches ax4 trigger timing)
enh_start_ms = (ENH_SHUTTER_DELAY + ENH_START) * 1000
enh_end_ms = (ENH_SHUTTER_DELAY + ENH_START + ENH_DURATION) * 1000
ann = lambda ax: _annotate_ax(ax, tYAG_1, tYAG_2, DOUBLE_YAG, enh_start_ms, enh_end_ms)

# --- Figure setup ---
fig = plt.figure(figsize=(12, 8))
gs = gridspec.GridSpec(2, 2, width_ratios=[0.9, 1.0])

# --- Subplot 1 (top left): Absorption RF (drift-corrected) ---
ax1 = fig.add_subplot(gs[0, 0])
if 'Absorption1' in trace_data and 'Absorption2' in trace_data:
    analog_data = trace_data['Absorption1']
    analog_data_2 = trace_data['Absorption2']
    times = analog_data[0].flatten()
    times_2 = analog_data_2[0].flatten()
    values = analog_data[1].flatten()
    values_2 = analog_data_2[1].flatten()

    values_corrected = process_trace(times * 1000, values, tYAG_ms=tYAG_1 * 1000)
    values_2_corrected = process_trace(times_2 * 1000, values_2, tYAG_ms=tYAG_1 * 1000)

    
    ax1.plot(times * 1000, values_corrected, 'b', label='Absorption1')
    ax1.plot(times_2 * 1000, values_2_corrected, 'g', label='Absorption2')

    # Auto-tighten ylim if both traces fit within [-0.5, 0.5]
    vis1 = values_corrected[(times * 1000 >= 0) & (times * 1000 <= XLIM_MS_ABS)]
    vis2 = values_2_corrected[(times_2 * 1000 >= 0) & (times_2 * 1000 <= XLIM_MS_ABS)]
    if vis1.size and vis2.size:
        if min(np.nanmin(vis1), np.nanmin(vis2)) >= -0.5 and max(np.nanmax(vis1), np.nanmax(vis2)) <= 0.5:
            ax1.set_ylim([-0.3, 0.3])

ax1.set_xlim([0, XLIM_MS_ABS])
ax1.set_xlabel('Time [ms]', fontsize=12)
ax1.set_ylabel('Offset Value', fontsize=12)
ax1.set_title('Absorption_RF', fontsize=14)
ax1.grid(True)
ax1.legend(loc='upper right')
ann(ax1)

# --- Subplot 2 (bottom left): Absorption DC (raw) ---
ax3 = fig.add_subplot(gs[1, 0])
if 'Absorption0' in trace_data:
    analog_data_dcprobe = trace_data['Absorption0']
    times_dcprobe = analog_data_dcprobe[0].flatten()
    values_dcprobe = analog_data_dcprobe[1].flatten()
    ax3.plot(times_dcprobe * 1000, values_dcprobe, 'b')

ax3.set_xlim([0, XLIM_MS_ABS])
ax3.set_xlabel('Time [ms]', fontsize=12)
ax3.set_ylabel('Value', fontsize=12)
ax3.set_title('Absorption_DC_component', fontsize=14)
ax3.grid(True)
# ax3.legend(loc='upper right')
ann(ax3)


# --- Subplot 5 (bottom right): Absorption atom (raw) ---
ax5 = fig.add_subplot(gs[1, 1])
if 'Absorption3' in trace_data:
    analog_data_dcprobe = trace_data['Absorption3']
    times_dcprobe = analog_data_dcprobe[0].flatten()
    values_dcprobe = analog_data_dcprobe[1].flatten()
    ax5.plot(times_dcprobe * 1000, values_dcprobe, 'b', label='Absorption_ATOM')

ax5.set_xlim([0, XLIM_MS_ABS])
ax5.set_xlabel('Time [ms]', fontsize=12)
ax5.set_ylabel('Value', fontsize=12)
ax5.set_title('Absorption_ATOM', fontsize=14)
ax5.grid(True)
ax5.legend(loc='upper right')
ann(ax5)
# # --- Subplot 3 (bottom right): NI_SCOPE (PXIe-5922) ---
# ax2 = fig.add_subplot(gs[1, 1])
# try:
#     voltages = run.get_trace('NI_SCOPE', raw_data=True)
#     with h5py.File(h5_path, 'r') as f:
#         props = labscript_utils.properties.get(f, 'NI_SCOPE', 'connection_table_properties')
#         sample_rate = float(props['min_sample_rate'])
#     times_SCOPE = np.arange(len(voltages[0])) / sample_rate * 1000  # samples -> ms
#     ax2.plot(times_SCOPE, voltages[0], label='Ch0', alpha=0.5)
#     ax2.set_ylim([-0.25, 0.01])
#     ax2.legend()
# except Exception as e:
#     print(f"Warning: NI_SCOPE trace not available: {e}")
#     ax2.text(0.5, 0.5, 'NI_SCOPE data\nnot available',
#              transform=ax2.transAxes, ha='center', va='center', fontsize=12)

# ax2.set_xlim([0, XLIM_MS_LIF])
# ax2.set_title('NI-5922 Readout', fontsize=16)
# ax2.set_xlabel('Time [ms]', fontsize=16)
# ax2.set_ylabel('Voltage [V]', fontsize=16)
# ann(ax2)

# --- Subplot 4 (top right): Digital trigger signals ---
inner_gs = gridspec.GridSpecFromSubplotSpec(2, 1, subplot_spec=gs[0, 1], hspace=0)
ax4_top = fig.add_subplot(inner_gs[0])
ax4_bot = fig.add_subplot(inner_gs[1], sharex=ax4_top)

if tstart is not None and tend is not None:
    tend_ms = (tend - tstart) * 1000
    t_ms = np.linspace(0, tend_ms, 10000)

    def _step(t, t0_s, duration_s):
        sig = np.zeros_like(t)
        lo = (t0_s - tstart) * 1000
        hi = lo + duration_s * 1000
        sig[(t >= lo) & (t < hi)] = 1.0
        return sig

    YAG_PULSE = 0.5e-3
    yag1 = _step(t_ms, tYAG_1, YAG_PULSE)
    yag2 = _step(t_ms, tYAG_2, YAG_PULSE if DOUBLE_YAG else np.zeros_like(t_ms))
    enh = _step(t_ms, ENH_SHUTTER_DELAY + ENH_START, ENH_DURATION)
    lif = np.ones_like(t_ms) if LIF_SHUTTER_OPEN else np.zeros_like(t_ms)

    ax4_top.step(t_ms, yag1, 'b-', where='post', label='YAG1')
    ax4_top.step(t_ms, yag2, 'r-', where='post', label='YAG2')
    ax4_bot.step(t_ms, enh, 'g-', where='post', label='enhancement')
    ax4_bot.step(t_ms, lif, 'm-', where='post', label='LIF probe')

    for ax in (ax4_top, ax4_bot):
        ax.set_yticks([0, 1])
        ax.set_ylim([-0.15, 1.3])
        ax.set_xlim([0, XLIM_MS_LIF])
        ax.legend(loc='upper right', fontsize=9)
        ax.grid(True)

    plt.setp(ax4_top.get_xticklabels(), visible=False)
    ax4_top.set_title(f"Trigger inputs (tend={tend_ms:.1f} ms)", fontsize=11)
    ax4_bot.set_xlabel('Time [ms]', fontsize=11)
else:
    ax4_top.set_title("Trigger inputs (tstart/tend not available)", fontsize=11)
    ax4_top.axis('off')
    ax4_bot.axis('off')

plt.tight_layout()
