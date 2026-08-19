from labscript import *
from labscriptlib.Main_Experiment.connection_table_open_cell2 import connection_table
from labscriptlib.Main_Experiment.subsequences.subsequences import digital_pulse, latch_digital

connection_table()  # Initialize devices from connection table

# === Labscript sequence ===
t = 0
add_time_marker(t, "Start", verbose=True)


##### Trigger the scope ####
t_trigger = 0.5e-3      #0.5ms
############################

# Ensure at least 4 samples for DO buffer
start()
TiSa_1_Setpoint.constant(freq_ramp if SCAN_TISA_1 else TISA_1)
TiSa_2_Setpoint.constant(freq_ramp if SCAN_TISA_2 else 378.836387)
Vexlum_Setpoint.constant(freq_ramp if SCAN_VEXLUM else VEXLUM)

YAG_1_voltage.constant(V_YAG1)
if DOUBLE_YAG:
    YAG_2_voltage.constant(V_YAG2)      # Set YAG voltage from global
# Raster_X.constant(RASTER_X)         # Set raster X position from global
# Raster_Y.constant(RASTER_Y)         # Set raster Y position from global

latch_digital(LIF_shutter, LIF_SHUTTER_OPEN)  # pre-set during transition_to_buffered

# #YAG triggering
# YAG1_line.go_low(0)
# YAG1_line.go_highW(tYAG) #replace with tYAG
# YAG1_line.go_low(tYAG + pulse_duration)

# # Dummy pulse (to satisfy sample buffer size: DAQmx requires at least 4 samples to be written before starting the task.)
# dummy_end = t_trigger + 2 * pulse_duration
# YAG1_line.go_high(dummy_end)
# YAG1_line.go_low(dummy_end + pulse_duration)

if DOUBLE_YAG:
    digital_pulse(YAG2_line, tYAG_2, 0.5e-3)
    digital_pulse(YAG1_line, tYAG_1, 0.5e-3)
    
else:
    digital_pulse(YAG1_line, tYAG_1, 0.5e-3)

if ENH_SHUTTER_OPEN:
    digital_pulse(ENH_line, ENH_START, ENH_DURATION)  # ENH pulse


# DAQ triggering: -2.5 V baseline
daq_ao0.constant(tstart, +2.5)
daq_ao0.constant(tstart + 0.5e-3, -2.5)


daq_ai0.acquire('Absorption_DCprobe',tstart,tend)
daq_ai1.acquire('Absorption',tstart,tend)
daq_ai2.acquire('Absorption2',tstart,tend) #added 07/14/2025
daq_ai3.acquire('Absorption3',tstart,tend) #added 07/17/2025


# stop(tend+ 50e-3)   # change to whatever you want
stop(tend+ 50e-3)   # change to whatever you want
