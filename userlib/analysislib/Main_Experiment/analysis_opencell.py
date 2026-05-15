import lyse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.transforms as transforms
import labscript_utils.h5_lock  # noqa: F401 — enables safe concurrent HDF5 access
import labscript_utils.properties

# --- Plot constants ---
XLIM_MS_ABS = 80  # ms

# --- Annotation helper ---
def _annotate_ax(ax, tYAG_1, tYAG_2, double_yag):
    """Add YAG dotted lines with text labels."""
    trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)

    ax.axvline(x=tYAG_1 * 1000, color='r', linestyle=':', linewidth=1.2)
    ax.text(
        tYAG_1 * 1000, 0.96, ' YAG1',
        transform=trans, color='r', fontsize=9,
        va='top', ha='left'
    )

    if double_yag:
        ax.axvline(x=tYAG_2 * 1000, color='darkred', linestyle=':', linewidth=1.2)
        ax.text(
            tYAG_2 * 1000, 0.96, ' YAG2',
            transform=trans, color='darkred', fontsize=9,
            va='top', ha='left'
        )

# --- Lyse boilerplate ---
if lyse.utils.worker.spinning_top:
    h5_path = lyse.path
else:
    df = lyse.data()
    h5_path = df.filepath.iloc[-1]

run = lyse.Run(h5_path)

# --- Extract traces ---
TRACE_NAMES = ['Absorption_DC_Front', 'Absorption_DC_Cell']
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
DOUBLE_YAG = bool(global_dict.get('DOUBLE_YAG', False))

fig = plt.figure(1, figsize=(12, 8))
fig.clf()

ax_front = fig.add_subplot(2, 1, 1)
ax_cell  = fig.add_subplot(2, 1, 2, sharex=ax_front)

fig.subplots_adjust(hspace=0.3)

# --- Front and Cell plots ---
if 'Absorption_DC_Front' in trace_data and 'Absorption_DC_Cell' in trace_data:
    analog_data_front = trace_data['Absorption_DC_Front']
    analog_data_cell = trace_data['Absorption_DC_Cell']

    times_front = analog_data_front[0].flatten() * 1000  # ms
    values_front = analog_data_front[1].flatten()

    times_cell = analog_data_cell[0].flatten() * 1000  # ms
    values_cell = analog_data_cell[1].flatten()

    # --- Front ---
    ax_front.plot(times_front, values_front, 'b', label='Front')
    ax_front.set_xlim([0, XLIM_MS_ABS])
    ax_front.set_ylabel('Signal [V]', fontsize=12)
    ax_front.set_title('Absorption (Front)', fontsize=14)
    ax_front.grid(True)
    _annotate_ax(ax_front, tYAG_1, tYAG_2, DOUBLE_YAG)

    vis_front = values_front[(times_front >= 0) & (times_front <= XLIM_MS_ABS)]
    if vis_front.size:
        ymin = np.nanmin(vis_front)
        ymax = np.nanmax(vis_front)
        if np.isfinite(ymin) and np.isfinite(ymax):
            pad = 0.05 * (ymax - ymin) if ymax > ymin else 0.05
            ax_front.set_ylim(ymin - pad, ymax + pad)

    # --- Cell ---
    ax_cell.plot(times_cell, values_cell, 'g', label='Cell')
    ax_cell.set_xlim([0, XLIM_MS_ABS])
    ax_cell.set_xlabel('Time [ms]', fontsize=12)
    ax_cell.set_ylabel('Signal [V]', fontsize=12)
    ax_cell.set_title('Absorption (Cell)', fontsize=14)
    ax_cell.grid(True)
    _annotate_ax(ax_cell, tYAG_1, tYAG_2, DOUBLE_YAG)

    vis_cell = values_cell[(times_cell >= 0) & (times_cell <= XLIM_MS_ABS)]
    if vis_cell.size:
        ymin = np.nanmin(vis_cell)
        ymax = np.nanmax(vis_cell)
        if np.isfinite(ymin) and np.isfinite(ymax):
            pad = 0.05 * (ymax - ymin) if ymax > ymin else 0.05
            ax_cell.set_ylim(ymin - pad, ymax + pad)

    if ax_front.lines:
        ax_front.legend(loc='upper right')
    if ax_cell.lines:
        ax_cell.legend(loc='upper right')

else:
    ax_front.text(
        0.5, 0.5, 'Missing absorption traces',
        transform=ax_front.transAxes,
        ha='center', va='center', fontsize=12
    )
    ax_front.set_title('Absorption (Front)', fontsize=14)
    ax_front.set_xlim([0, XLIM_MS_ABS])
    ax_front.set_ylabel('Signal [V]', fontsize=12)
    ax_front.grid(True)
    _annotate_ax(ax_front, tYAG_1, tYAG_2, DOUBLE_YAG)

    ax_cell.text(
        0.5, 0.5, 'Missing absorption traces',
        transform=ax_cell.transAxes,
        ha='center', va='center', fontsize=12
    )
    ax_cell.set_title('Absorption (Cell)', fontsize=14)
    ax_cell.set_xlim([0, XLIM_MS_ABS])
    ax_cell.set_xlabel('Time [ms]', fontsize=12)
    ax_cell.set_ylabel('Signal [V]', fontsize=12)
    ax_cell.grid(True)
    _annotate_ax(ax_cell, tYAG_1, tYAG_2, DOUBLE_YAG)

# Do not use plt.tight_layout() in Lyse here
plt.show()