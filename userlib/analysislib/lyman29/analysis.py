#Post-shot analysis code. Adjusted from Lyse website 
# example, "Single shot analysis with global file opening"

import lyse
import numpy as np
import matplotlib.pyplot as plt

# Is this script being run from within an interactive lyse session?
if lyse.spinning_top:
    # If so, use the filepath of the current shot
    h5_path = lyse.path
else:
    # If not, get the filepath of the last shot of the lyse DataFrame
    df = lyse.data()
    h5_path = df.filepath.iloc[-1]

run = lyse.Run(h5_path)

# # Get a dictionary of the global variables used in this shot
# run_globals = run.get_globals()
# print(run_globals)

# extract the traces
trace_data = {}
trace_data["Absorption"] = run.get_trace("Absorption")
trace_data["Absorption2"] = run.get_trace("Absorption2") #added 07/14/2025
trace_data["Absorption3"] = run.get_trace("Absorption3") #added 08/07/2025

#extract the image
image_data = run.get_image("camera","fluorescence", "frame")

fig = plt.figure(4, figsize=(10, 4))
# Create a gridspec layout with 1 row and 2 columns, and set the width ratio
gs = fig.add_gridspec(1, 2, width_ratios=[2, 1])

#get global variable
global_dict = run.get_globals()
tYAG = float(global_dict['tYAG'])

################Comment this out if you don't want to view##################
## First subplot (top-left) - analog output vs time
# ax1 = fig.add_subplot(gs[0, 0])  # The first subplot
# for (name, analog_data) in trace_data.items():
#     times = analog_data[0].reshape(1, np.shape(analog_data)[1])
#     times = times.flatten()
#     values = analog_data[1].reshape(1, np.shape(analog_data)[1])
#     values = values.flatten()
#     # print(type(values))
#     ax1.plot(times*1000, values, 'b')
#     ax1.axvline(x=tYAG*1000, color='r', linestyle='--', label='Ablation')
#     ax1.set_xlim([0, 25])
#     ax1.set_ylim([-0.5,0.5])
# ax1.set_xlabel('Time [ms]', fontsize=16)
# ax1.set_ylabel('Values', fontsize=16)
# ax1.set_title('Analog Output vs Time')
# ax1.grid(True)

# # Second subplot (top-right) - fluorescence image
# ax2 = fig.add_subplot(gs[0, 1])  # The second subplot
# ax2.imshow(image_data, extent=[0, 512, 0, 512], cmap='magma',vmin=1568,vmax=1700) # you may want to chenge vmin, vmax depending on your LIF probe power
# ax2.set_title('Fluorescence Image', fontsize=16)
# ax2.set_xlabel('x', fontsize=16)
# ax2.set_ylabel('y', fontsize=16)
# # Adjust layout
# plt.tight_layout()  # Automatically adjusts subplot params for better spacing
# plt.show()
#########################################################################################
##Version 2 for including two absorption plots for FM quadratures
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from scipy.optimize import curve_fit

# Define linear function for drift fitting
def line_func(x, A, B):
    return A * x + B

fig = plt.figure(figsize=(10, 8))
gs = gridspec.GridSpec(2, 2, width_ratios=[1.5, 1])

# --- First subplot (top left) for Absorption and Absorption2---
ax1 = fig.add_subplot(gs[0, 0])
if 'Absorption' in trace_data:
    analog_data = trace_data['Absorption']
    analog_data_2 = trace_data['Absorption2']
    times = analog_data[0].flatten() 
    times_2 = analog_data_2[0].flatten()
    values = analog_data[1].flatten()
    values_2 = analog_data_2[1].flatten()

    #collect useful indices. Could have also done times.searchsorted()
    trigger_index = np.searchsorted(times,2/1000)
    beforeYAG_index = np.searchsorted(times,1.95/1000) # hardcoded values are on the absorption data timeframe.
    after_abs_index = np.searchsorted(times,10/1000)
    end_index = np.searchsorted(times,15/1000)

    # ---- Process Absorption ----
    fit_time = np.concatenate((times[:beforeYAG_index], times[after_abs_index:end_index]))
    fit_data = np.concatenate((values[:beforeYAG_index], values[after_abs_index:end_index]))
    popt, _ = curve_fit(line_func, fit_time, fit_data)
    flat_values = values - line_func(times, *popt)
    offset = flat_values[:trigger_index].mean()
    values_corrected = flat_values - offset

    # ---- Process Absorption2 ----
    # You can reuse the same index logic if times_2 ≈ times
    beforeYAG_index_2 = np.where(times_2 < tYAG - 0.5/1000)[0][-1]
    after_abs_index_2 = np.where(times_2 > tYAG + 0.5/1000)[0][0]
    end_index_2 = len(times_2)
    trigger_index_2 = np.where(times_2 < tYAG)[0][-1]

    fit_time_2 = np.concatenate((times_2[:beforeYAG_index_2], times_2[after_abs_index_2:end_index_2]))
    fit_data_2 = np.concatenate((values_2[:beforeYAG_index_2], values_2[after_abs_index_2:end_index_2]))
    popt_2, _ = curve_fit(line_func, fit_time_2, fit_data_2)
    flat_values_2 = values_2 - line_func(times_2, *popt_2)
    offset_2 = flat_values_2[:trigger_index_2].mean()
    values_2_corrected = flat_values_2 - offset_2

     # ---- Plotting ----
    ax1.plot(times * 1000, values_corrected, 'b', label='Absorption')
    ax1.plot(times_2 * 1000, values_2_corrected, 'g', label='Absorption2')
    ax1.axvline(x=tYAG * 1000, color='r', linestyle='--', label='YAG')

    # Plot formatting
    ax1.set_xlim([0, 15])
    # ax1.set_ylim([-0.05, 0.05])
    ax1.set_xlabel('Time [ms]', fontsize=12)
    ax1.set_ylabel('Offset Value', fontsize=12)
    ax1.set_title('Absorption_RF', fontsize=14)
    ax1.grid(True)
    ax1.legend(loc='upper right')

# --- Second subplot (bottom left) for Absorption3 ---
ax3 = fig.add_subplot(gs[1, 0])
if 'Absorption3' in trace_data:
    analog_data_3 = trace_data['Absorption3']
    times_3 = analog_data_3[0].flatten()
    values_3 = analog_data_3[1].flatten()
    ax3.plot(times_3 * 1000, values_3, 'g')
    ax3.axvline(x=tYAG * 1000, color='r', linestyle='--', label='YAG')
    ax3.set_xlim([0, 15])
    # ax3.set_ylim([-0.3, 0.3])
    ax3.set_xlabel('Time [ms]', fontsize=12)
    ax3.set_ylabel('Value', fontsize=12)
    ax3.set_title('Absorption_DC', fontsize=14)
    ax3.grid(True)
    ax3.legend(loc='upper right')

# --- Third subplot (right side spanning both rows) for fluorescence image ---
ax2 = fig.add_subplot(gs[:, 1])   # span both rows vertically
ax2.imshow(image_data,
           extent=[0, 512, 0, 512],
           cmap='magma',
           vmin=1568,
           vmax=1700)
ax2.set_title('Fluorescence Image', fontsize=16)
ax2.set_xlabel('x', fontsize=16)
ax2.set_ylabel('y', fontsize=16)

# Adjust layout
plt.tight_layout()  # Automatically adjusts subplot params for better spacing
plt.show()
#########################################################################################






# Compute a result based on the data processing and save it to the 'results' group of
# the shot file
analog_int = trace_data["Absorption"][1].mean()
analog_int_err = trace_data["Absorption"][1].std()/np.sqrt(len(trace_data["Absorption"][1])) #Why divide with sqrt of N?
run.save_result('BaF_abs integrated', analog_int)
run.save_result('BaF_abs integrated err', analog_int_err)

# print(np.shape(image_data))
### For scatter reduction purposes
#pixel_sum = np.sum(image_data) #just to look at the sum
photon_counting_threshold = 1690
# photon_counting_threshold = 1810#1570 #for 1x1 binning! #1810 for 4x4 binning
pixel_sum = np.mean(image_data > photon_counting_threshold)
###
run.save_result('pixel_sum', pixel_sum)


 