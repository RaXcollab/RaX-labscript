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
    parent_device=pb_clock_line,
    clock_terminal=f'/{ni_6363_max_name}/PFI1',
    MAX_name=f'{ni_6363_max_name}',
    acquisition_rate=acq_rate,
    stop_order=-1,
)

# Analog Output Channels
# The AnalogOut objects must be referenced below with the name of the object (e.g. 'ao0')
AnalogOut(name='ao0', parent_device=ni_6363, connection='ao0')
AnalogOut(name='ao1', parent_device=ni_6363, connection='ao1')

# Digital Output Channels
DigitalOut(
    name='do0', parent_device=ni_6363, connection='port0/line0'
)
DigitalOut(
    name='do1', parent_device=ni_6363, connection='port0/line1'
)

# Analog Input Channels
AnalogIn(name="ai0", parent_device=ni_6363, connection='ai0')
AnalogIn(name="ai1", parent_device=ni_6363, connection='ai1')


start()
add_time_marker(0, "data acq", verbose=True)
ai0.acquire(label='data', start_time=0, end_time=25e-3)
dt = 0.1e-3
do1.go_high(2e-3)
do1.go_low(2e-3+dt)
t_ramp_i=2.5e-3
add_time_marker(t_ramp_i, "A0 Ramp", verbose=True)
ao0.ramp(
    t=t_ramp_i, 
    initial=0, 
    final=1, 
    duration=10e-3, 
    samplerate=10e3
)
add_time_marker(25e-3, "A0 Ramp", verbose=True)
stop(50e-3)