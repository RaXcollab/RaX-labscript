**Read source before using unfamiliar labscript classes. Training data may have wrong signatures.**

Source: `~/miniconda/envs/labscript/Lib/site-packages/labscript/` and `labscript-devices/labscript_devices/`.

## Connection Table Classes

- `PrawnBlaster(name, com_port, num_pseudoclocks=1, trigger_device=None, clock_frequency=100e6, use_wait_monitor=True, ...)` — pseudoclock device. Access clocklines via `pb.clocklines[N]`. Max 30,000/num_pseudoclocks instructions. Resolution ~20ns
- `NI_PXIe_6361(name, parent_device, clock_terminal, MAX_name, num_AI=0, num_AO=0, AI_term='RSE', acquisition_rate=None, ports=None, stop_order=None, ...)` — analog+digital I/O. Capabilities auto-applied; kwargs override. AI term: ai0-7 support RSE/NRSE/Diff; ai8-15 RSE/NRSE only
- `NI_PXIe_6535(name, parent_device, clock_terminal, MAX_name, ports=None, ...)` — digital-only. 4 buffered ports (8 lines each) + port4 (6 lines, static)
- `AnalogOut(name, parent_device, connection, limits=None, default_value=None, unit_conversion_class=None, ...)` — timed analog output
- `AnalogIn(name, parent_device, connection, scale_factor=1.0, units="Volts", ...)` — data acquisition
- `DigitalOut(name, parent_device, connection, inverted=False, ...)` — timed digital output
- **`Shutter(name, parent_device, connection, delay=(0,0), open_state=1, ...)`** — `delay` is a **TUPLE** `(open_delay_s, close_delay_s)`, NOT separate kwargs. Subclass of DigitalOut
- `Trigger(name, parent_device, connection, trigger_edge_type="rising", ...)` — trigger pulse for TriggerableDevices
- `ClockLine(name, pseudoclock, connection, ramping_allowed=True, ...)` — auto-created by PrawnBlaster; rarely instantiated manually
- `RemoteControl(name, host, reqrep_port, pubsub_port, mock=True, ...)` — external GUI base class
- `RemoteAnalogOut(name, parent_device, connection, units="V", limits=(0,inf), decimals=3, step_size=0.01, ...)` — static output to remote GUI
- `RemoteAnalogMonitor(name, parent_device, connection, units="V", limits=(0,inf), decimals=3, ...)` — monitor from remote GUI

## Sequence Functions & Methods

Called between `start()` and `stop()`:

- `start()` → float — must be called before any output instructions
- `stop(t)` — ends experiment at time t, triggers compilation
- `add_time_marker(t, label, color=None, verbose=False)` — RunViewer annotation
- `wait(label, t, timeout=5.0)` → float — pause until external trigger or timeout
- `AnalogOut.constant(t, value, units=None)` — set constant value at time t
- `AnalogOut.ramp(t, duration, initial, final, samplerate, units=None, truncation=1.0)` → duration
- `AnalogOut.sine_ramp(t, duration, initial, final, samplerate, units=None, truncation=1.0)` → duration
- `AnalogOut.sine4_reverse_ramp(t, duration, initial, final, samplerate, units=None, truncation=1.0)` → duration
- `AnalogOut.exp_ramp(t, duration, initial, final, samplerate, zero=0, units=None, truncation=None)` → duration
- `AnalogOut.square_wave(t, duration, amplitude, frequency, phase, offset, duty_cycle, samplerate, ...)` → duration
- `AnalogOut.customramp(t, duration, function, *args, samplerate=..., truncation=1.0)` → duration — function receives `(t_relative, duration, *args)`
- `DigitalOut.go_high(t)` / `.go_low(t)` — set digital state at time t
- `DigitalOut.enable(t)` / `.disable(t)` — HIGH/LOW respecting `inverted` flag
- `DigitalOut.repeat_pulse_sequence(t, duration, pulse_sequence, period, samplerate)` — repeat pattern
- `Shutter.open(t)` / `.close(t)` — accounts for mechanical delay automatically
- `Trigger.trigger(t, duration)` — produce trigger pulse
- `AnalogIn.acquire(label, start_time, end_time)` → duration
- `RemoteAnalogOut.constant(value, units=None)` — **static: no time parameter** (contrast with timed `AnalogOut.constant(t, value)`)
- `StaticDigitalOut.go_high()` / `.go_low()` — **static: no time parameter**

## Key Constraints & Gotchas

- **Shutter t=0 clamping**: `t_calc = t - delay if t >= delay else 0`. `open(0)` with 15ms delay fires at t=0 (imprecise), NOT at -15ms. Source: `outputs.py:1576`
- **NI_DAQmx DO port atomicity**: All lines per port written together via `WriteDigitalU32`. Changing one line re-sends all 8 bits. Source: `NI_DAQmx/blacs_workers.py:110`
- **Static vs timed**: `RemoteAnalogOut.constant(value)` — no time param. `AnalogOut.constant(t, value)` — requires time. `StaticAnalogOut` — set once per shot
- **Ramp return values**: Return actual duration (with truncation). Chain: `t += ao.sine_ramp(t, ...)`
- **Unit conversions**: If `unit_conversion_class` set, must pass `units=` in method calls
- **Clock quantization**: ~20ns resolution (PrawnBlaster). Internal rounding to 0.1ns
- **Ramp overlap**: Two ramps on same output cannot overlap — raises LabscriptError
- **DDS gate**: `DDSQuantity.pulse()` auto-gates if gate exists. `amplitude=0` disables without `disable()`
- **PrawnBlaster limits**: 30,000 / num_pseudoclocks instructions; clock_limit = 10 MHz

## Source Locations

- **labscript core**: `~/miniconda/envs/labscript/Lib/site-packages/labscript/` — `outputs.py`, `core.py`, `remote.py`
- **labscript-devices**: `labscript-devices/labscript_devices/` (dev install) — NI_DAQmx, PrawnBlaster, RemoteControl

## Unit Constants

From `labscript.constants`: `ms=1e-3`, `us=1e-6`, `ns=1e-9`, `MHz=1e6`, `kHz=1e3`, `mV=1e-3`, `V=1`, `mA=1e-3`
