# External application integration

**Status:** Current integration reference
**Last reviewed:** 2026-08-21

This repository contains labscript-side interfaces for three external application types.

The external applications remain separate programs. They own their environments, hardware libraries, and operator configuration.

## Supported interfaces

| Application type | Labscript device | Purpose |
|---|---|---|
| Laser lock | `LaserLockDevice` | Set frequency targets and read lock state. |
| Raster controller | `RasteringDevice` | Set target coordinates and save raster metadata. |
| BigSky YAG controller | `BigSkyHub` | Program laser values and read controller state. |

`user_devices.RemoteControl` supplies the shared client, worker, tab, and transport behavior.

## Process boundary

BLACS and each external application run in separate processes.

The BLACS worker sends commands through a ZeroMQ request socket. It receives monitor updates through a subscriber socket.

The external application owns direct hardware access. The labscript device must not load the external application's hardware libraries.

## Configuration boundary

Configure these values in the connection table or local profile:

- Hostname or IP address
- Request and reply port
- Publish and subscribe port
- Connection names
- Device-specific timeouts
- Mock or hardware mode

The RaX reference apparatus uses localhost because its external applications run on the same computer.

Collaborators must change these values for another network or apparatus.

## Wire contract

All supported applications must implement RemoteControl protocol v2.

The protocol defines discovery, value reads, value writes, status values, errors, and monitor topics.

Use [RemoteControl ZMQ protocol v2](remotecontrol-zmq-protocol-v2.md) as the only wire authority.

Connection names form part of the wire contract. Change both sides in the same coordinated release.

## Shot lifecycle

During manual mode, BLACS sends operator changes to the external application.

During buffered transition, BLACS sends values stored in the shot file.

During a shot, the external application remains responsible for hardware execution and status publication.

After a shot, BLACS writes available monitor snapshots into the shot HDF5 file.

Use [Shot HDF5 layout](shot-h5-layout.md) for the data contract.

## Failure behavior

Use typed v2 status and error fields for decisions.

Treat transport timeouts, unknown commands, and malformed replies as communication failures.

Each device can define explicit tolerated conditions. Do not infer tolerated errors from free text.

Buffered failures can stop a shot. Manual failures must remain visible to the operator.

## Generic collaborator scaffold

A collaborator can implement another external application without copying a RaX GUI.

Implement these parts:

1. A v2 server that exposes named connections.
2. Request handlers for supported read and write operations.
3. Typed failure replies.
4. Optional monitor publication.
5. A matching labscript connection-table entry.
6. Contract tests for each connection name.

Keep hardware code behind the server boundary. Keep the shared protocol independent of the GUI toolkit.

## Verification

Run the RemoteControl and device tests before a protocol change.

```powershell
python -m pytest -q userlib\user_devices\RemoteControl\tests
python -m pytest -q userlib\user_devices\LaserLockDevice\tests
python -m pytest -q userlib\user_devices\RasteringDevice\tests
python -m pytest -q userlib\user_devices\BigSkyHub\tests
```

Some device directories can have no focused tests. In that case, run the full user-device test tree.

```powershell
python -m pytest -q userlib\user_devices
```

For hardware verification, use the approved procedure for the applicable external application.
