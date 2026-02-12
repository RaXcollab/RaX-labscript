from labscript import (
    DigitalOut,
    AnalogOut,
    AnalogIn,
    start,
    stop,
    add_time_marker
)

def absorption_signal(ao_chan: AnalogOut):
    t=0
    ao_chan.constant(t=t, value=SIGNAL_VI)
    t=DIP_TI
    add_time_marker(t, f"Absorption Signal for {ao_chan.name}", verbose=True)
    t+=ao_chan.sine4_reverse_ramp(
        t=t,
        initial=DIP_VF,
        final=SIGNAL_VI,
        duration=DIP_DOWN_DUR,
        samplerate=DIP_RATE,
        truncation=0.8
    )
    t+=ao_chan.sine_ramp(
        t=t,
        initial=DIP_VF,
        final=SIGNAL_VI,
        duration=DIP_UP_DUR,
        samplerate=DIP_RATE,
    )
    return t


def digital_pulse(digital_chan: DigitalOut,tstart,tdur):
    digital_chan.go_high(tstart)
    tend = tstart+tdur
    digital_chan.go_low(tend)
    return tend