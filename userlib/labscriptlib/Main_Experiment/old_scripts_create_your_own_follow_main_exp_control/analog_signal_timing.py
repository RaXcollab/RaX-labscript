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
AnalogIn(name="ai2", parent_device=ni_6363, connection='ai2')
AnalogIn(name="ai3", parent_device=ni_6363, connection='ai3')

'''
Define the Experiment Logic
'''
def digital_start_ref():
    t=0
    do1.go_high(t)
    t+=10e-3
    do1.go_low(t)
    return t

def analog_output_ramp():
    t=1e-3
    add_time_marker(t, "A0 Ramp", verbose=True)
    t+=ao0.ramp(
        t=t, 
        initial=0, 
        final=2, 
        duration=5e-3, 
        samplerate=2e6
    )
    # at 5 ms
    ao0.constant(t=t, value=0)
    return t

def analog_output_ramp_1():
    t=7e-3
    add_time_marker(t, "A0 Ramp", verbose=True)
    t+=ao1.ramp(
        t=t, 
        initial=0, 
        final=0.5, 
        duration=2e-3, 
        samplerate=2e6
    )
    # at 9ms
    ao1.constant(t=t, value=0)
    return t

def collect_AO_0():
    t=0
    t+=ai0.acquire(label='AO_ramp', start_time=t, end_time=10e-3)
    return t
def collect_AO_1():
    t=0
    t+=ai1.acquire(label='AI_signal', start_time=t, end_time=10e-3)

    return t

t=0
start()
t=max(t, digital_start_ref())
t=max(t, analog_output_ramp())
t=max(t, analog_output_ramp_1())
t=max(t, collect_AO_0())
t=max(t, collect_AO_1())
# t=max(t, collect_dummy_inputs())
print(t)
stop(t)