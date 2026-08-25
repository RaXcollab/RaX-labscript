# RemoteControl

RemoteControl connects a BLACS tab to an external application.

It uses ZeroMQ REQ-REP for commands. It uses ZeroMQ PUB-SUB for monitor values and heartbeats.

Use these components:

- `RemoteControl` defines the external application endpoint.
- `RemoteAnalogOut` defines a writable value.
- `RemoteAnalogMonitor` defines a read-only value.

Use [the protocol v2 specification](../../../docs/remotecontrol-zmq-protocol-v2.md) as the wire authority.

Use [the external application guide](../../../docs/external-guis-architecture.md) for integration structure.

Use `127.0.0.1` for local applications. Store other host values in local apparatus configuration.
