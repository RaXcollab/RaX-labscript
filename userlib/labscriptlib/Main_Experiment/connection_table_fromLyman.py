from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, AnalogIn
# from labscript_devices.PrawnBlaster import PrawnBlaster
from labscript_devices.PrawnBlaster.labscript_devices import PrawnBlaster #08/18/2025 Shungo
# from labscript_devices.NI_DAQmx.labscript_devices import NI_PXIe_6361
from labscript_devices.NI_DAQmx.models.NI_PXIe_6361 import NI_PXIe_6361
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
from user_devices.RemoteControl.labscript_devices import RemoteControl, RemoteAnalogOut, RemoteAnalogMonitor
from user_devices.NuvuCamera.labscript_devices import NuvuCamera

#Updated by Shungo on 01/09/2025 - Added NUVU Camera and MKS Pressure gauge

pb = PrawnBlaster(
        name='pb',
        com_port='COM7',
        num_pseudoclocks=1
    )

'''
Initialize the NI Hardware and all the channels
to be used on each card
'''
ni_6361_max_name = "PXI1Slot8"
ni_6361_clockline = pb.clocklines[0] 

ni_6361 = NI_PXIe_6361(
    name='ni_6361', 
    parent_device=ni_6361_clockline,
    clock_terminal=f'/{ni_6361_max_name}/PFI1',
    MAX_name=f'{ni_6361_max_name}',
    acquisition_rate=100e3,
    stop_order=-1,
    AI_term = 'Diff',
    num_AI = 4,
    num_AO = 0,
    num_CI=1,
)


# Laser Raster GUI

# RemoteControl(name='LaserRasterGUI', host='localhost', reqrep_port=1234,pubsub_port=1235)
# RemoteAnalogOut(name='raster', parent=remote_laser_raster_GUI, connection='move_to_next')
# raster.constant(37)

# RemoteAnalogOut(name='laser_x_control', parent=remote_laser_raster_GUI, connection='laser_x_pos')
# RemoteAnalogOut(name='laser_y_control', parent=remote_laser_raster_GUI, connection='laser_y_pos')
# RemoteAnalogMonitor(name='laser_x_actual_value', parent=remote_laser_raster_GUI, connection='laser_x_actual_value')
# RemoteAnalogMonitor(name='laser_y_actual_value', parent=remote_laser_raster_GUI, connection='laser_y_actual_value')

# x_coord = RUNMANAGER_GLOBALS[RASTER_PATTERN_X_COORD]
# y_coord = RUNMANAGER_GLOBALS[RASTER_PATTERN_Y_COORD]


# laser_x_control.constant(x_coord)
# laser_y_control.constant(y_coord)

# ###Commented out by Shungo on 05/30/2025#####################
# # # Remote Operation of Laser Lock GUI 
# RemoteControl(name='LaserLockGUI', host="192.168.69.3", reqrep_port=3796,pubsub_port=3797, mock=False) # add IP address and Port of the host software

# RemoteAnalogOut(
#     name='Vexlum_Setpoint', 
#     parent_device=LaserLockGUI, 
#     connection=6,
#     units="THz",
#     decimals=9
# )

# RemoteAnalogMonitor(
#     name='Vexlum_Value', 
#     parent_device=LaserLockGUI, 
#     connection=6,
#     units="THz",
#     decimals=9
# )

# RemoteAnalogOut(
#     name='Matisse_Setpoint', 
#     parent_device=LaserLockGUI, 
#     connection=4,
#     units="THz",
#     decimals=9
# )

# RemoteAnalogMonitor(
#     name='Matisse_Value', 
#     parent_device=LaserLockGUI, 
#     connection=4,
#     units="THz",
#     decimals=9
# )
# ###############################################################
# Analog Output Channels
# The AnalogOut objects must be referenced below with the name of the object (e.g. 'ao0')
# AnalogOut(name='ao0', parent_device=ni_6361, connection='ao0')
# AnalogOut(name='ao1', parent_device=ni_6361, connection='ao1')

# Digital Output Channels
YAG_trig = DigitalOut(
    name='do1', parent_device=ni_6361, connection='port0/line1'
)
camera_trig = DigitalOut(
    name='do2', parent_device=ni_6361, connection='port0/line2'
)
# NI wants an even number of DO, so this is code is available for that purpose
# TODO: automatically check if DO number is even and handle it if not
# extra_digital = DigitalOut(
#     name='do2', parent_device=ni_6361, connection='port0/line2'
# )

# Analog Input Channels
mol_abs = AnalogIn(name="ai0", parent_device=ni_6361, connection='ai0')
atom_abs = AnalogIn(name="ai1", parent_device=ni_6361, connection='ai1')
DC_abs = AnalogIn(name="ai2", parent_device=ni_6361, connection='ai2')



# # Nuvu Camera
# # NOTE: The initialization of the NuvuCamera creates an implicit DO under the name "camera_trigger" at the specified connection.
# camera = NuvuCamera(
#    name="camera",
#    parent_device=ni_6361,
#    connection="port0/line2", 
#    serial_number=0xDEADBEEF, # NUVU camera initialization does not require serial_number, no need to touch this
#    camera_attributes={
#        "readoutMode":1, #1 = EM
#        "exposure_time":20, #Shafin: "Um miliseconds?"
#        "timeout": 1000, #See above for units
#        "square_bin": 1, #NxN bin size
#        'target_detector_temp':-60, 
#        "emccd_gain": 5000, #Max 5000
#        "trigger_mode":2, # 1 = EXT_LOW_HIGH, #0 = INT, 2 "EXT_LOW_HIGH_EXP" (minus for HIGH_LOW),
#        "shutter_mode": 1,
#    },
#    manual_mode_camera_attributes={
#        "readoutMode":1,
#        "exposure_time":20,
#        "timeout": 1000,
#        "square_bin": 1,
#        'target_detector_temp':-60,
#        "emccd_gain": 5000,
#        "trigger_mode":0,
#        "shutter_mode":1,
#    },
#    mock=False #True
# )


# Remote Operation of Laser Lock GUI
# RemoteControl(name='LaserLockGUI', host="localhost", reqrep_port=55535, pubsub_port=55536, mock=False) # add IP address and Port of the host software
# RemoteControl(name='LaserLockGUI', host="192.168.69.3", reqrep_port=3796, pubsub_port=3796, mock=False) # add IP address and Port of the host software

# RemoteAnalogOut(
#     name='cwave_generator_setpoints', 
#     parent_device=LaserLockGUI, 
#     connection='cwave_gtr_set',
#     units="THz",
#     decimals=6
# )
# RemoteAnalogOut(
#     name='Titanium_Sapphire_setponts', 
#     parent_device=LaserLockGUI, 
#     connection='TiSa_set',
#     units="nm",
#     decimals=6
# )

# RemoteAnalogMonitor(
#     name='cwave_generator_actual_values', 
#     parent_device=LaserLockGUI, 
#     connection='cwave_gtr_act',
#     units="nm",
#     decimals=6
# )
# RemoteAnalogMonitor(
#     name='Titanium_Sapphire_actual_values', 
#     parent_device=LaserLockGUI, 
#     connection='TiSa_act',
#     units="nm",
#     decimals=6
# )

if __name__ == '__main__':
    # Begin issuing labscript primitives
    # start() elicits the commencement of the shot
    start()

    # Stop the experiment shot with stop()
    stop(1.0)

