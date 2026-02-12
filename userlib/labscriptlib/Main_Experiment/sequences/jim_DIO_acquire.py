# from labscript import *
# from labscriptlib.Main_Experiment.subsequences.subsequences import digital_pulse
# from labscript_devices.PrawnBlaster.labscript_devices import PrawnBlaster
# from labscript_devices.NI_DAQmx.models.NI_PXIe_6361 import NI_PXIe_6361
# from labscript_devices.NI_DAQmx.models.NI_PXIe_6535 import NI_PXIe_6535
# # from user_devices.NI_SCOPE.labscript_devices import NI_SCOPE
# from user_devices.edge_counter.labscript_devices import EdgeCounter


# # === Initialize pseudoclock ===
# pb = PrawnBlaster(
#     name='pb',
#     com_port='COM7',
#     num_pseudoclocks=2
# )

# ni_6361_clockline = pb.clocklines[0] 
# ni_6535_clockline = pb.clocklines[1] 

# # === NI 6361 Setup ===
# ni_6361_max_name = "PXI1Slot8"

# ni_6361 = NI_PXIe_6361(
#     name='ni_6361', 
#     parent_device=ni_6361_clockline, #Pseudoclock 0
#     clock_terminal=f'/{ni_6361_max_name}/PFI1',
#     MAX_name=f'{ni_6361_max_name}',
#     acquisition_rate=100e3,
#     stop_order=-1,
#     AI_term = 'Diff',
#     num_AI = 4,
#     num_AO = 2
# )

# EdgeCounter(
#     name='pulse_counter',
#     parent_device=ni_6361_clockline,      # attach to the SAME NI 6361 device
#     counter='ctr0',          # or 'ctr1' if you prefer the other counter
#     MAX_name=ni_6361_max_name,  # "PXI1Slot8"
#     pfi='PFI3',                 # BNC-2090A PFI3 → board PFI3
#     edge='rising',              # or 'falling' if needed
#     save_path='/results/counter/total',
#     sync_to_ai=True             # arms off AI StartTrigger for aligned window
# )


# # === NI 6535 Setup ===
# ni_6535_max_name = "PXI1Slot5"

# ni_6535 = NI_PXIe_6535(
#     name='ni_6535',
#     parent_device=ni_6535_clockline,  #Pseudoclock 1
#     clock_terminal=f'/{ni_6535_max_name}/PFI4',  # adjust if needed
#     MAX_name=ni_6535_max_name,
#     stop_order=1
# )

# # Define digital output line on PXIe-6535
# DigitalOut('YAG1_line', ni_6535, 'port0/line1') 
# DigitalOut('YAG2_line', ni_6535, 'port0/line2') 
# DigitalOut('ENH_line', ni_6535, 'port0/line3') 
# DigitalOut('dummy_line', ni_6535, 'port0/line4')    #for even number


# # NI_SCOPE(
# #     name='NI_SCOPE',
# #     MAX_name='PXI1Slot2',
# #     vertical_range=[1.0, 10.0],         # Vpp for [Ch0, Ch1]
# #     vertical_coupling=['AC', 'AC'],      # Supported strings: 'DC', 'AC', 'GND', 'HF_REJECT', 'LF_REJECT'. (Need to check if working..)
# #     min_sample_rate=1_000_000,             # Hz
# #     min_num_pts=500_000,                 # record length
# #     trigger_source='TRIG',
# #     trigger_level=1.0,           # triggers at +1V
# #     trigger_delay=0.0,            # 0s time offset between trigger event and when sampling starts
# # )


# AnalogIn('daq_ai0',ni_6361,'ai0') # not used
# AnalogIn('daq_ai1',ni_6361,'ai1')
# AnalogIn('daq_ai2',ni_6361,'ai2')
# AnalogIn('daq_ai3',ni_6361,'ai3')

# AnalogOut('daq_ao0',ni_6361,'ao0') #Used for NI-5922 TRIG
# AnalogOut('daq_ao1',ni_6361,'ao1') # not used

# # === Labscript sequence ===
# t = 0
# add_time_marker(t, "Start", verbose=True)


# # ##### Trigger the scope ####
# # t_trigger = 0.5e-3      #0.5ms
# # ############################

# # Ensure at least 4 samples for DO buffer
# start()

# # #YAG triggering
# # YAG1_line.go_low(0)
# # YAG1_line.go_high(tYAG) #replace with tYAG
# # YAG1_line.go_low(tYAG + pulse_duration)

# # # Dummy pulse (to satisfy sample buffer size: DAQmx requires at least 4 samples to be written before starting the task.)
# # dummy_end = t_trigger + 2 * pulse_duration
# # YAG1_line.go_high(dummy_end)
# # YAG1_line.go_low(dummy_end + pulse_duration)

# digital_pulse(YAG1_line, tYAG, 0.5e-3)
# digital_pulse(YAG2_line, tYAG, 0.5e-3)  
# digital_pulse(ENH_line, ENH_start, ENH_end) 


# # DAQ triggering: -2.5 V baseline
# daq_ao0.constant(tstart, +2.5)
# daq_ao0.constant(tstart + 0.5e-3, -2.5)



# daq_ai1.acquire('Absorption',tstart,tend) 
# daq_ai2.acquire('Absorption2',tstart,tend) #added 07/14/2025
# daq_ai3.acquire('Absorption3',tstart,tend) #added 07/17/2025


# stop(tend+ 50e-3)   # change to whatever you want


from labscript import *
from labscriptlib.Main_Experiment.connection_table import *   # <-- IMPORT devices from CT
from labscriptlib.Main_Experiment.subsequences.subsequences import digital_pulse

# (Do NOT import NI_PXIe_6361 / NI_PXIe_6535 / EdgeCounter here; already in CT)

t = 0
add_time_marker(t, "Start", verbose=True)

start()

digital_pulse(YAG1_line, tYAG, 0.5e-3)
digital_pulse(YAG2_line, tYAG, 0.5e-3)
digital_pulse(ENH_line,  ENH_start, ENH_end)

daq_ao0.constant(tstart, +2.5)
daq_ao0.constant(tstart + 0.5e-3, -2.5)

daq_ai1.acquire('Absorption',  tstart, tend)
daq_ai2.acquire('Absorption2', tstart, tend)
daq_ai3.acquire('Absorption3', tstart, tend)

stop(tend + 50e-3)
