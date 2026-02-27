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


def latch_digital(digital_chan: DigitalOut, value):
    """Set a digital channel to a constant state for the entire shot.

    Used for channels controlled by RunManager globals rather than
    timed pulse sequences. The channel must also be listed in the
    parent device's 'latched_lines' device property so the NI_DAQmx
    worker applies the value during transition_to_buffered (before the
    pseudoclock starts) and restores the manual-mode value after the shot.

    The time argument MUST be 0. The worker pre-latch reads DO_table[0]
    (the first time sample) to determine the latch value. A non-zero time
    would leave the first sample at the default (low), and the pre-latch
    would read the wrong state.
    """
    if value:
        digital_chan.go_high(0)
    else:
        digital_chan.go_low(0)