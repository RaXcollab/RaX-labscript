## Sequence file for first open cell work in 38 oxford, 04/2026


from labscript import *
from labscriptlib.Main_Experiment.connection_table import connection_table
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
TiSa_1_Setpoint.constant(TISA_1)  # Set desired frequency here
# Vexlum_Setpoint.constant(VEXLUM)    # Set desired frequency here
YAG_1_voltage.constant(V_YAG1)
if DOUBLE_YAG:
    YAG_2_voltage.constant(V_YAG2)      # Set YAG voltage from global
# Raster_X.constant(RASTER_X)         # Set raster X position from global
# Raster_Y.constant(RASTER_Y)         # Set raster Y position from global

# latch_digital(LIF_shutter, LIF_SHUTTER_OPEN)  # pre-set during transition_to_buffered

#YAG triggering
YAG1_line.go_low(0)
YAG1_line.go_high(tYAG_1) #replace with tYAG
YAG1_line.go_low(tYAG_1 *2)

# Dummy pulse (to satisfy sample buffer size: DAQmx requires at least 4 samples to be written before starting the task.)
pulse_duration = 20e-3
dummy_end = t_trigger + 2 * pulse_duration
# ENH_line.go_high(dummy_end)
# ENH_line.go_low(dummy_end + pulse_duration)

if DOUBLE_YAG:
    digital_pulse(YAG2_line, tYAG_2, 0.5e-3)
    digital_pulse(YAG1_line, tYAG_1, 0.5e-3)
else:
    digital_pulse(YAG1_line, tYAG_1, 0.5e-3)
    digital_pulse(ENH_line, tYAG_1 + 2e-3, 0.5e-3)   # dummy pulse just to pad DO samples...

# if ENH_SHUTTER_OPEN:
    # digital_pulse(ENH_line, ENH_START, ENH_DURATION)  # ENH pulse


# DAQ triggering: -2.5 V baseline
daq_ao0.constant(tstart, +2.5)
daq_ao0.constant(tstart + 0.5e-3, -2.5)


daq_ai0.acquire('Absorption0',tstart,tend)
daq_ai1.acquire('Absorption1',tstart,tend)
daq_ai2.acquire('Absorption2',tstart,tend) 
daq_ai3.acquire('Absorption3',tstart,tend) 
daq_ai4.acquire('Absorption_DC_Cell',tstart,tend) 
daq_ai5.acquire('Absorption_DC_Front',tstart,tend) 


# stop(tend+ 50e-3)   # change to whatever you want
stop(tend+ 50e-3)   # change to whatever you want
