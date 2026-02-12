from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, AnalogIn
from labscript_devices.PineBlaster import PineBlaster
from labscript_devices.NI_DAQmx.labscript_devices import NI_PCIe_6363
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice

# Use a pineblaster for the psuedoclock
PineBlaster(name='pb', usbport='COM9')

'''
Initialize the NI Hardware and all the channels
to be used on each card
'''
ni_6363_max_name = "PXI1Slot2"

NI_PCIe_6363(
    name='ni_6363', 
    parent_device=pb_clock_line, # each device needs a parent pseudoclock, as this is what defines when the device is run
    clock_terminal=f'/{ni_6363_max_name}/PFI1', # the clock is physically connected to the PFI1 channel
    MAX_name=f'{ni_6363_max_name}',
    acquisition_rate=1000e3,
    stop_order=-1,
)

# Analog Output Channels
AnalogOut(name='voltage_ramp', parent_device=ni_6363, connection='ao0')
AnalogOut(name='ao1', parent_device=ni_6363, connection='ao1')

# Digital Output Channels
DigitalOut(
    name='sprout_shutter', parent_device=ni_6363, connection='port0/line0' #manually connected to user1
)
DigitalOut(
    name='do1', parent_device=ni_6363, connection='port0/line1'
)

# Analog Input Channels
AnalogIn(name="ai0", parent_device=ni_6363, connection='ai0')
AnalogIn(name="ai1", parent_device=ni_6363, connection='ai1')
AnalogIn(name="ai2", parent_device=ni_6363, connection='ai2')
AnalogIn(name="ai3", parent_device=ni_6363, connection='ai3')

def operate_shutter(t):
    sprout_shutter.go_high(t)
    t+=open_dur
    sprout_shutter.go_low(t)
    return t

t=0
start()
t = open_delay
t = operate_shutter(t)
stop(t)