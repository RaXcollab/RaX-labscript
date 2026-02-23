import lyse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import h5py
import labscript_utils.h5_lock  # noqa: F401 — enables safe concurrent HDF5 access
import labscript_utils.properties
from filtering import process_trace

# --- Plot constants ---
XLIM_MS = 20.0

# --- Lyse boilerplate ---
if lyse.utils.worker.spinning_top:
    h5_path = lyse.path
else:
    df = lyse.data()
    h5_path = df.filepath.iloc[-1]

run = lyse.Run(h5_path)

# --- Extract traces (graceful handling for missing traces) ---
TRACE_NAMES = ['Absorption', 'Absorption2', 'Absorption3']
trace_data = {}
for name in TRACE_NAMES:
    try:
        trace_data[name] = run.get_trace(name)
    except Exception:
        print(f"Warning: trace '{name}' not found in {h5_path}")

# --- Globals ---
global_dict = run.get_globals()
tYAG = float(global_dict['tYAG'])
ENH_START = float(global_dict['ENH_START'])
ENH_DURATION = float(global_dict['ENH_DURATION'])

# --- Figure setup ---
fig = plt.figure(figsize=(12, 8))
gs = gridspec.GridSpec(2, 2, width_ratios=[0.9, 1.0])

# --- Subplot 1 (top left): Absorption RF (drift-corrected) ---
ax1 = fig.add_subplot(gs[0, 0])
if 'Absorption' in trace_data and 'Absorption2' in trace_data:
    analog_data = trace_data['Absorption']
    analog_data_2 = trace_data['Absorption2']
    times = analog_data[0].flatten()
    times_2 = analog_data_2[0].flatten()
    values = analog_data[1].flatten()
    values_2 = analog_data_2[1].flatten()

    # Drift correction via adaptive fitting (times are in seconds, process_trace expects ms)
    values_corrected = process_trace(times * 1000, values, tYAG_ms=tYAG * 1000)
    values_2_corrected = process_trace(times_2 * 1000, values_2, tYAG_ms=tYAG * 1000)

    ax1.plot(times * 1000, values_corrected, 'b', label='Absorption')
    ax1.plot(times_2 * 1000, values_2_corrected, 'g', label='Absorption2')
    ax1.axvline(x=tYAG * 1000, color='r', linestyle='--', label='YAG')
    ax1.axvspan((tYAG + ENH_START) * 1000, (tYAG + ENH_START + ENH_DURATION) * 1000,
                color='yellow', alpha=0.3, label='ENH window')

ax1.set_xlim([0, XLIM_MS])
ax1.set_xlabel('Time [ms]', fontsize=12)
ax1.set_ylabel('Offset Value', fontsize=12)
ax1.set_title('Absorption_RF', fontsize=14)
ax1.grid(True)
ax1.legend(loc='upper right')

# --- Subplot 2 (bottom left): Absorption DC (raw) ---
ax3 = fig.add_subplot(gs[1, 0])
if 'Absorption3' in trace_data:
    analog_data_3 = trace_data['Absorption3']
    times_3 = analog_data_3[0].flatten() - 2e-3  # Subtract tYAG offset (2 ms); update if pre-YAG timing changes
    values_3 = analog_data_3[1].flatten()
    ax3.plot(times_3 * 1000, values_3, 'g')
    ax3.axvline(x=tYAG * 1000, color='r', linestyle='--', label='YAG')

ax3.set_xlim([0, XLIM_MS])
ax3.set_xlabel('Time [ms]', fontsize=12)
ax3.set_ylabel('Value', fontsize=12)
ax3.set_title('Absorption_DC', fontsize=14)
ax3.grid(True)
ax3.legend(loc='upper right')

# --- Subplot 3 (bottom right): NI_SCOPE (PXIe-5922) ---
ax2 = fig.add_subplot(gs[1, 1])
try:
    voltages = run.get_trace('NI_SCOPE', raw_data=True)
    with h5py.File(h5_path, 'r') as f:
        props = labscript_utils.properties.get(f, 'NI_SCOPE', 'connection_table_properties')
        sample_rate = float(props['min_sample_rate'])
    times_SCOPE = np.arange(len(voltages[0])) / sample_rate * 1000  # samples -> ms
    ax2.plot(times_SCOPE, voltages[0], label='Ch0', alpha=0.5)
    ax2.set_ylim([-0.1, 0.01])
    ax2.axvline(x=tYAG * 1000, color='r', linestyle='--', label='YAG')
    ax2.legend()
except Exception as e:
    print(f"Warning: NI_SCOPE trace not available: {e}")
    ax2.text(0.5, 0.5, 'NI_SCOPE data\nnot available',
             transform=ax2.transAxes, ha='center', va='center', fontsize=12)

ax2.set_xlim([0, XLIM_MS])
ax2.set_title('NI-5922 Readout', fontsize=16)
ax2.set_xlabel('Time [ms]', fontsize=16)
ax2.set_ylabel('Voltage [V]', fontsize=16)

plt.tight_layout()
