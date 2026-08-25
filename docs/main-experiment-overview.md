# Main_Experiment reference apparatus

**Status:** Current reference
**Last reviewed:** 2026-08-21

This apparatus shows how the RaX fork connects timing hardware and external applications.

Copy it before you adapt it to another computer.

## Connection table

The current file is `userlib/labscriptlib/Main_Experiment/connection_table.py`.

It contains these timing devices:

- One PrawnBlaster with two pseudoclocks.
- One NI PXIe-6361 for analog input and analog output.
- One NI PXIe-6535 for digital output.

The NI Measurement and Automation Explorer names and serial port are local values.

Set them for each computer before you compile the connection table.

## NI-SCOPE

The connection table contains a disabled NI-SCOPE example for an NI-5922 digitizer.

Enable it only after you install the NI-SCOPE driver and Python API.

Set the resource name, channels, range, sample rate, record length, and trigger for the local system.

NI-SCOPE writes a two-dimensional `float64` array to `/data/traces/NI_SCOPE`.

See [NI-SCOPE conventions](ni-scope-conventions.md) for the dataset contract.

## External applications

The connection table includes local scaffolding for these applications:

- `LaserLockGUI` for laser setpoints and monitor values.
- `RasteringGUI` for raster coordinates and position monitors.
- `BigSkyLasers` for YAG laser control.

The examples use `127.0.0.1`. Store other host values in local apparatus files.

Use [the protocol v2 specification](remotecontrol-zmq-protocol-v2.md) for all wire messages.

## Camera

The reference table includes a Nuvu camera.

This device is optional for the base collaborator installation.

Remove it from a copied apparatus if the computer does not use that camera.

## Sequences

The retained sequences match the current reference table:

- `Open_cell.py` demonstrates analog acquisition, YAG pulses, and an NI-SCOPE trigger pulse.
- `Open_cell2.py` demonstrates a compact camera and acquisition shot.
- `Closed_cell.py` demonstrates a second YAG trigger and an enhancement pulse.

RunManager supplies sequence globals at compile time.

Static checks can report these names as undefined.

## Shared helpers

`subsequences/subsequences.py` contains reusable pulse and waveform helpers.

Use `digital_pulse(channel, start, duration)` for a digital pulse.

## Data paths

NI DAQmx analog inputs use compound `(t, values)` datasets under `/data/traces/`.

The NI-SCOPE device uses the raw array contract described above.

External application setpoints use `/devices/<device>/remote_device_operation`.

See [the shot HDF5 contract](shot-h5-layout.md) for all retained paths.
