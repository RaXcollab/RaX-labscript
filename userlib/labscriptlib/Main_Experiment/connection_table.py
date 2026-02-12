from labscript import *
from labscriptlib.Main_Experiment.subsequences.subsequences import digital_pulse
from labscript_devices.PrawnBlaster.labscript_devices import PrawnBlaster
from labscript_devices.NI_DAQmx.models.NI_PXIe_6361 import NI_PXIe_6361
from labscript_devices.NI_DAQmx.models.NI_PXIe_6535 import NI_PXIe_6535
from user_devices.NI_SCOPE.labscript_devices import NI_SCOPE
# from user_devices.RemoteControl.labscript_devices import RemoteControl, RemoteAnalogOut, RemoteAnalogMonitor


# === Initialize pseudoclock ===
pb = PrawnBlaster(
    name='pb',
    com_port='COM7',
    num_pseudoclocks=2
)

ni_6361_clockline = pb.clocklines[0] 
ni_6535_clockline = pb.clocklines[1] 

# === NI 6361 Setup ===
ni_6361_max_name = "PXI1Slot8"

ni_6361 = NI_PXIe_6361(
    name='ni_6361', 
    parent_device=ni_6361_clockline, #Pseudoclock 0
    clock_terminal=f'/{ni_6361_max_name}/PFI1',
    MAX_name=f'{ni_6361_max_name}',
    acquisition_rate=100e3,
    stop_order=-1,
    AI_term = 'Diff',
    num_AI = 4,
    num_AO = 2
)

# === NI 6535 Setup ===
ni_6535_max_name = "PXI1Slot5"

ni_6535 = NI_PXIe_6535(
    name='ni_6535',
    parent_device=ni_6535_clockline,  #Pseudoclock 1
    clock_terminal=f'/{ni_6535_max_name}/PFI4',  # adjust if needed
    MAX_name=ni_6535_max_name,
    stop_order=1
)


# # === Laser Lock Communication === #
# RemoteControl(name='LaserLockGUI', host="127.0.0.1", reqrep_port=3796,pubsub_port=3797, mock=False) # add IP address and Port of the host software

# # Name convention: <wavemeter channel>_Setpoint and <wavemeter channel>_Value

# RemoteAnalogOut(
#     name='Vexlum_Setpoint', 
#     parent_device=LaserLockGUI, 
#     connection=3,
#     units="THz",
#     decimals=9
# )

# RemoteAnalogOut(
#     name='TiSa_1_Setpoint', 
#     parent_device=LaserLockGUI, 
#     connection=4,
#     units="THz",
#     decimals=9
# )

# RemoteAnalogMonitor(
#     name='Vexlum_Value', 
#     parent_device=LaserLockGUI, 
#     connection=3,
#     units="THz",
#     decimals=9
# )

# RemoteAnalogMonitor(
#     name='TiSa_1_Value', 
#     parent_device=LaserLockGUI, 
#     connection=4,
#     units="THz",
#     decimals=9
# )

# Define digital output line on PXIe-6535
DigitalOut('YAG1_line', ni_6535, 'port0/line1') 
DigitalOut('YAG2_line', ni_6535, 'port0/line2') 
DigitalOut('ENH_line', ni_6535, 'port0/line3') 
DigitalOut('dummy_line', ni_6535, 'port0/line4')    #for even number


NI_SCOPE(
    name='NI_SCOPE',
    MAX_name='PXI1Slot2',
    vertical_range=[0.5, 0.1],         # Vpp for [Ch0, Ch1]
    vertical_coupling=['DC', 'DC'],      # Supported strings: 'DC', 'AC', 'GND', 'HF_REJECT', 'LF_REJECT'. (Need to check if working..)
    min_sample_rate=1_000_000,             # Hz
    min_num_pts=200_000,                 # record length
    trigger_source='TRIG',
    trigger_level=1.0,           # triggers at +1V
    trigger_delay=0.0,            # 0s time offset between trigger event and when sampling starts
)


AnalogIn('daq_ai0',ni_6361,'ai0') # not used
AnalogIn('daq_ai1',ni_6361,'ai1')
AnalogIn('daq_ai2',ni_6361,'ai2')
AnalogIn('daq_ai3',ni_6361,'ai3')

AnalogOut('daq_ao0',ni_6361,'ao0') #Used for NI-5922 TRIG
AnalogOut('daq_ao1',ni_6361,'ao1') # not used

if __name__ == '__main__':
    # Begin issuing labscript primitives
    # start() elicits the commencement of the shot
    start()

    # Stop the experiment shot with stop()
    stop(1.0)

