from labscript import *
from labscriptlib.Main_Experiment.connection_table import *
from labscriptlib.Main_Experiment.subsequences.subsequences import digital_pulse

# === Labscript sequence ===
t = 0
add_time_marker(t, "Start", verbose=True)


##### Trigger the scope ####
t_trigger = 0.5e-3      #0.5ms
############################

# Ensure at least 4 samples for DO buffer
start()
# TiSa_1_Setpoint.constant(FREQ_RAMP)  # Set desired frequency here
# Vexlum_Setpoint.constant(FREQ_RAMP)    # Set desired frequency here

# #YAG triggering
# YAG1_line.go_low(0)
# YAG1_line.go_high(tYAG) #replace with tYAG
# YAG1_line.go_low(tYAG + pulse_duration)

# # Dummy pulse (to satisfy sample buffer size: DAQmx requires at least 4 samples to be written before starting the task.)
# dummy_end = t_trigger + 2 * pulse_duration
# YAG1_line.go_high(dummy_end)
# YAG1_line.go_low(dummy_end + pulse_duration)

if DOUBLE_YAG:
    digital_pulse(YAG2_line, tYAG, 0.5e-3)
    digital_pulse(YAG1_line, tYAG + YAG_DELAY, 0.5e-3)
else:
    digital_pulse(YAG1_line, tYAG, 0.5e-3)

digital_pulse(ENH_line, ENH_START, ENH_DURATION)  # ENH pulse


# DAQ triggering: -2.5 V baseline
daq_ao0.constant(tstart, +2.5)
daq_ao0.constant(tstart + 0.5e-3, -2.5)



daq_ai1.acquire('Absorption',tstart,tend)
daq_ai2.acquire('Absorption2',tstart,tend) #added 07/14/2025
daq_ai3.acquire('Absorption3',tstart,tend) #added 07/17/2025


# stop(tend+ 50e-3)   # change to whatever you want
stop(tend+ 1)   # change to whatever you want
