##### Unknown import, can probably delete ##################
# from multiprocessing import connection

##### Import from the official Labscript Devices ###########
# from labscript_devices.PrawnBlaster.labscript_devices import PrawnBlaster
# from labscript_devices.NI_DAQmx.models.NI_PXIe_6361 import NI_PXIe_6361
# from labscript_devices.NI_DAQmx.models.NI_PCIe_6363 import NI_PCIe_6363
# from labscript_devices.NI_DAQmx.models.NI_PXIe_6739 import NI_PXIe_6739
# from labscript_devices.NI_DAQmx.models.NI_PXIe_6535 import NI_PXIe_6535

##### Import from the custom RaX user_devices ###############
# from user_devices.RemoteControl.labscript_devices import RemoteControl, RemoteAnalogOut, RemoteAnalogMonitor
# from user_devices.NuvuCamera.labscript_devices import NuvuCamera

if True:
    from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, AnalogIn
    from labscript_devices.PrawnBlaster import PrawnBlaster
    from labscript_devices.NI_DAQmx.labscript_devices import NI_PCIe_6363
    from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice

    from user_devices.RemoteControl.labscript_devices import RemoteControl, RemoteAnalogOut, RemoteAnalogMonitor
    from user_devices.NuvuCamera.labscript_devices import NuvuCamera


    pb = PrawnBlaster(
            name='pb',
            com_port='COM12',
            num_pseudoclocks=1
        )

    '''
    Initialize the NI Hardware and all the channels
    to be used on each card
    '''
    ni_6363_max_name = "PXI1Slot2"
    ni_6363_clockline = pb.clocklines[0] 

    ni_6363 = NI_PCIe_6363(
        name='ni_6363', 
        parent_device=ni_6363_clockline,
        clock_terminal=f'/{ni_6363_max_name}/PFI1',
        MAX_name=f'{ni_6363_max_name}',
        acquisition_rate=100e3,
        stop_order=-1,
        AI_term = 'Diff',
        num_AI = 2,
        num_AO = 0,
        num_CI=1,
    )

    # RemoteControl(name='LaserRasterGUI', host='localhost', reqrep_port=1234,pubsub_port=1235)
    # RemoteAnalogOut(name='raster', parent=remote_laser_raster_GUI, connection='move_to_next')
    # raster.constant(37)

    # Analog Output Channels
    # The AnalogOut objects must be referenced below with the name of the object (e.g. 'ao0')
    # AnalogOut(name='ao0', parent_device=ni_6363, connection='ao0')
    # AnalogOut(name='ao1', parent_device=ni_6363, connection='ao1')

    # Digital Output Channels
    YAG_trig = DigitalOut(
        name='do1', parent_device=ni_6363, connection='port0/line1'
    )
    # camera_trig = DigitalOut(
    #     name='do2', parent_device=ni_6363, connection='port0/line2'
    # )

    # Analog Input Channels
    mol_abs = AnalogIn(name="ai0", parent_device=ni_6363, connection='ai0')
    atom_abs = AnalogIn(name="ai1", parent_device=ni_6363, connection='ai1')

    # Nuvu Camera
    # NOTE: The initialization of the NuvuCamera creates an implicit DO under the name "camera_trigger" at the specified connection.
    camera = NuvuCamera(
        name="camera",
        parent_device=ni_6363,
        connection="port0/line2", 
        serial_number=0xDEADBEEF, # NUVU camera initialization does not require serial_number, no need to touch this
        camera_attributes={
            "readoutMode":1, #1 = EM
            "exposure_time":20, #Shafin: "Um miliseconds?"
            "timeout": 1000, #See above for units
            "square_bin": 1, #NxN bin size
            'target_detector_temp':-60, 
            "emccd_gain": 5000, #Max 5000
            "trigger_mode":2, # 1 = EXT_LOW_HIGH, #0 = INT, 2 "EXT_LOW_HIGH_EXP" (minus for HIGH_LOW),
            "shutter_mode":1, #0= undefined, 1=open, 2=closed
        },
        manual_mode_camera_attributes={
            "readoutMode":1,
            "exposure_time":20,
            "timeout": 1000,
            "square_bin": 1,
            'target_detector_temp':-60,
            "emccd_gain": 5000,
            "trigger_mode":0,
            "shutter_mode":1,
        },
        mock=False
    ) 
    ##NuvuCamera is just a renamed +alpha of class IMAQxdCamera in labscript_devices.IMAQdxCamera.labscript_decives.py. 
    # Functions follow the definitions in that file.
    ## Manual attributes are defined in userlib/user_devices/NuvuCamera/Nuvu_sdk/Nuvu_cam_utils.py


from labscriptlib.lyman29.subsequences.subsequences import *

start()

# tbackground = 0
# camera.expose(tbackground,'fluorescence','background')

# tstart = 0
# tend = 12e-3
mol_abs.acquire('Absorption',tstart,tend) 
atom_abs.acquire('Absorption2',tstart,tend) #added 07/14/2025

# Pulse the YAG
# tYAG = 2e-3
digital_pulse(YAG_trig,tYAG, 0.5e-3) 

# tEMCCD = tYAG+0.1e-3
# digital_pulse(camera_trig,tEMCCD, 20e-3)
camera.expose(tEMCCD,'fluorescence',trigger_duration=20e-3) 


stop(30e-3)
