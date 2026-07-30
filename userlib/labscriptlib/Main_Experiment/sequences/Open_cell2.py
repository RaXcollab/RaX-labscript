## Open cell work, 07/2026

from labscript import *
from labscriptlib.Main_Experiment.connection_table import connection_table
from labscriptlib.Main_Experiment.subsequences.subsequences import digital_pulse, latch_digital

connection_table()  # Initialize devices from connection table

start()
TiSa_1_Setpoint.constant(freq_ramp if SCAN_TISA_1 else TISA_1)
TiSa_2_Setpoint.constant(freq_ramp if SCAN_TISA_2 else TISA_2)
Vexlum_Setpoint.constant(VEXLUM)
YAG_1_voltage.constant(V_YAG1)

daq_ai0.acquire('Absorption0',tstart,tend)
daq_ai1.acquire('Absorption1',tstart,tend)
daq_ai2.acquire('Absorption2',tstart,tend) 
daq_ai3.acquire('Absorption3',tstart,tend) 

digital_pulse(YAG1_line, tYAG_1, 0.5e-3)
digital_pulse(ENH_line, tYAG_1 + 2e-3, 0.5e-3)
# digital_pulse(ENH_line, ENH_SHUTTER_DELAY + ENH_START, ENH_DURATION)

# camera.expose is the ONLY line0 driver; in trigger_mode 2 (EXT_LOW_HIGH_EXP) trigger_duration IS the exposure
# tEMCCD and trigger_duration are runmanager globals
camera.expose(tEMCCD,'fluorescence',trigger_duration=trigger_duration)


stop(500e-3)
