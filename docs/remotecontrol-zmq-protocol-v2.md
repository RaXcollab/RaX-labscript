# RemoteControl ZMQ protocol v2

This document defines the current RemoteControl protocol between BLACS and the external GUI servers.

The protocol uses ZeroMQ (ZMQ) REQ-REP for commands. It uses ZMQ PUB-SUB for monitor data and heartbeats.

## REQ-REP wire format

Each REQ-REP message contains one UTF-8 JSON object in one ZMQ frame.

### Request envelope

```json
{
  "v": 2,
  "id": 17,
  "action": "PROGRAM_VALUE",
  "connection": "4",
  "value": 348.666410,
  "args": {"wait_for_lock": true},
  "request_timestamp": 1747948800.123
}
```

| Field | Requirement | Meaning |
|---|---|---|
| `v` | Required | Protocol version. The value must be `2`. |
| `action` | Required | Command name. |
| `id` | Required for BLACS | Request identifier. The server echoes it when present. |
| `connection` | Command-specific | Device connection name. |
| `value` | Command-specific | Value for `PROGRAM_VALUE`. |
| `args` | Optional | Command-specific options. |
| `request_timestamp` | Added by the shared encoder | Unix time in seconds. |

The BLACS client starts `id` at zero. It increments `id` for each `RemoteCommunication` request.

The server accepts a request without `id`. Its reply then omits `id`.

The shared encoder omits empty `connection`, `None` values, and empty `args` objects.

### Reply envelope

```json
{
  "v": 2,
  "id": 17,
  "status": "SUCCESS",
  "value": 348.666410,
  "server_timestamp": 1747948800.456
}
```

A failed request has a structured error:

```json
{
  "v": 2,
  "id": 17,
  "status": "TIMEOUT",
  "error": {
    "code": "lock_wait_timeout",
    "message": "timeout waiting for lock on ch4",
    "retryable": true
  },
  "server_timestamp": 1747948860.456
}
```

| Field | Requirement | Meaning |
|---|---|---|
| `v` | Required | Protocol version. The value is `2`. |
| `status` | Required | One status token from the table below. |
| `server_timestamp` | Added by the shared encoder | Unix time in seconds. |
| `id` | Conditional | Echo of a non-`None` request `id`. |
| `value` | Conditional | Command result. The encoder omits a `None` value. |
| `error` | Failure replies | Object with `code`, `message`, and `retryable`. |
| Other top-level fields | Command-specific | Extra result data for `HELLO`, `PING`, and raster commands. |

Current servers use these status tokens:

| Status | Meaning |
|---|---|
| `SUCCESS` | The server completed or accepted the command. |
| `ERROR` | The request, server state, or device operation caused an error. |
| `REJECTED` | The BigSky controller rejected a valid device command. |
| `TIMEOUT` | The server did not complete a requested wait before its limit. |
| `UNKNOWN_CONNECTION` | The connection is invalid or has no readable value. |

`error.retryable` is an advisory flag. The current BLACS client does not retry automatically.

## Common commands

| Action | Request fields | Success reply |
|---|---|---|
| `HELLO` | No command fields | `protocol_version`, `server`, `capabilities`, and optional `connections` |
| `PING` | No command fields | `server` and `uptime_seconds` |
| `PROGRAM_VALUE` | `connection`, `value`, optional `args` | Server-specific result |
| `CHECK_VALUE` | `connection` | `value` |

`HELLO` and `PING` are base-server commands. Servers implement `PROGRAM_VALUE` and `CHECK_VALUE` with registered handlers.

The BLACS client sends `HELLO` during connection setup. It does not send `PING` during normal operation.

The canonical capability names are `heartbeat`, `monitors`, and `wait_for_lock`.

| Server name | Capabilities | `connections` in `HELLO` |
|---|---|---|
| `BigSkyLasers` | `heartbeat`, `monitors` | Dynamic prefixes such as `YAG_1_*` |
| `LaserLockGUI` | `heartbeat`, `monitors`, `wait_for_lock` | Omitted |
| `RasteringGUI` | `heartbeat`, `monitors` | Omitted |

Connection advertisements are hints. The implemented matcher removes trailing `*` characters and performs a prefix match.

The BLACS `RemoteCommunication` client does not enforce these advertisements. Each server remains the connection authority.

### Common errors

| Condition | Status | Error code | Retryable |
|---|---|---|---|
| Invalid UTF-8, invalid JSON, or non-object JSON | `ERROR` | `envelope_parse_error` | No |
| Missing `v`, or `v` is not `2` | `ERROR` | `v1_protocol_refused` | No |
| Unknown or missing action | `ERROR` | `unknown_action` | No |
| Handler exception or invalid handler return | `ERROR` | `handler_exception` | No |

The server includes the request `id` in these errors when it can parse that field.

## LaserLockGUI commands

LaserLockGUI accepts connection strings `"1"` through `"8"`.

### `PROGRAM_VALUE`

`value` must convert to a number. The server emits a setpoint write for the selected port.

`args.wait_for_lock` controls the optional lock wait. An absent value means `false`.

The BLACS client always sends this option as `true` or `false`.

The server waits only when these three conditions are true:

- `args.wait_for_lock` is `true`.
- The port has `lock_enabled` set.
- Global `deviation_mode` is set.

The server returns `SUCCESS` after lock convergence. It returns `TIMEOUT/lock_wait_timeout` after 60 seconds.

If either gate is off, the server returns `SUCCESS` without a wait. It writes a warning to the GUI log.

| Condition | Status | Error code | Retryable |
|---|---|---|---|
| Connection is not an integer string | `UNKNOWN_CONNECTION` | `unknown_connection` | No |
| Port is outside 1 through 8 | `UNKNOWN_CONNECTION` | `port_out_of_range` | No |
| Value is not numeric | `ERROR` | `invalid_value` | No |
| Lock wait expires | `TIMEOUT` | `lock_wait_timeout` | Yes |

### `CHECK_VALUE`

`CHECK_VALUE` returns the stored setpoint from shared state. It does not return the wavemeter measurement.

A missing setpoint or a setpoint below 1 THz returns `UNKNOWN_CONNECTION/setpoint_not_initialized`. This error is retryable.

## BigSkyLasers commands

Each connection starts with a registered laser name, such as `YAG_1`.

### `PROGRAM_VALUE`

Writable connection suffixes are:

- `voltage`
- `shutter`
- `lamps`
- `qswitch`
- `lamp_mode`
- `qswitch_mode`
- `warmup`
- `start_lasing`
- `stop`
- `keep_warm`

For example, use `YAG_1_voltage`. A `_monitor` suffix is not writable.

| Condition | Status | Error code | Retryable |
|---|---|---|---|
| Laser prefix is unknown | `UNKNOWN_CONNECTION` | `unknown_connection` | No |
| Laser is disconnected | `ERROR` | `laser_disconnected` | Yes |
| Target has `_monitor` suffix | `ERROR` | `cannot_program_monitor` | No |
| Writable suffix is unknown | `ERROR` | `unknown_writable_param` | No |
| Controller command exceeds 10 seconds | `TIMEOUT` | `command_timeout` | Yes |
| Controller returns a general error | `ERROR` | `command_error` | No |

Controller refusals return `REJECTED`. Their `error.code` identifies the refusal and is not retryable.

Current refusal codes include:

- `did_not_take_effect`
- `voltage_out_of_range`
- `lamps_not_active`
- `lamp_mode_requires_standby`
- `invalid_lamp_mode`
- `qswitch_requires_lamps_and_shutter`
- `qswitch_mode_requires_standby`
- `invalid_qswitch_mode`
- `serial_failure`
- `parse_failure`

A legacy controller error that starts with `rejected` maps to `REJECTED/rejected_did_not_take_effect`.

### `CHECK_VALUE`

Readable suffixes are `temperature`, `voltage`, `lamps`, `shutter`, `qswitch`, `lamp_mode`, and `qswitch_mode`.

The connection can include an optional `_monitor` suffix. The reply contains the current controller value.

An unknown readable suffix returns `ERROR/unknown_monitor_param`. A disconnected laser returns retryable `ERROR/laser_disconnected`.

## RasteringGUI commands

RasteringGUI implements its device commands through `PROGRAM_VALUE`.

`args.timeout_sec` sets a motor or GUI response limit. Its default is 10 seconds.

### Coordinate commands

| Connection | Value | Behavior |
|---|---|---|
| `laser_raster_x_coord` | Number | Move the X motor axis. |
| `laser_raster_y_coord` | Number | Move the Y motor axis. |
| `laser_raster_xy` | Two finite numbers | Move both axes as one command. |

`laser_raster_xy` uses target coordinates by default. Set `args.frame` to `motor` for direct motor coordinates.

The accepted frame values are `pixel` and `motor`. The default `pixel` path passes coordinates through when no calibration exists.

Invalid coordinates return `ERROR/invalid_value`. An invalid frame returns `ERROR/invalid_frame`.

A failed motor move returns retryable `ERROR/motor_move_failed`.

### Raster control commands

| Connection | Value | Success reply fields |
|---|---|---|
| `arm_raster` | Mode request | `mode`; a new arm also returns `armed` and `dropped` |
| `move_to_next` | Ignored | Point metadata, `finished`, or `in_place` as applicable |
| `shots_per_step` | Integer of 1 or more | `shots_per_step` |
| `disarm_raster` | Ignored | `disarmed` |

The strings `1`, `true`, `continuous`, and `cont` request continuous mode. Other strings request step mode.

For non-string values, normal Boolean conversion selects the mode.

`arm_raster` can change the mode of an active step raster. It also transfers control to the remote client.

It cannot convert an active continuous raster to step mode. A new remote arm supports step mode only.

The GUI can drop unreachable points during a new arm. The reply reports accepted and dropped point counts.

`move_to_next` advances a remote step raster. A successful step can return these provenance fields:

- `point_index`
- `path_len`
- `frame`
- `target_xy`
- `calibration_matrix`
- `calibration_offset`

An exhausted iterator returns `SUCCESS` with `finished: true`.

Under local control, `move_to_next` does not move the raster. It returns the current point or `in_place: true`.

`disarm_raster` releases ownership to the GUI. It preserves the armed path and clears the remote shots-per-step display.

`disarm_raster` is idempotent. Its `disarmed` field is `false` when no raster was active.

| Condition | Status | Error code | Retryable |
|---|---|---|---|
| Unknown connection | `UNKNOWN_CONNECTION` | `unknown_connection` | No |
| No GUI raster configuration exists | `ERROR` | `no_raster_configured` | No |
| A new remote arm requests continuous mode | `ERROR` | `continuous_arm_requires_gui` | No |
| GUI arm call fails | `ERROR` | `arm_failed` or GUI-supplied code | No |
| GUI arm call exceeds its limit | `ERROR` | `arm_timeout` | No |
| Remote control has no active raster | `ERROR` | `raster_not_active` | No |
| Remote command would stop or convert continuous mode | `ERROR` | `raster_in_continuous_mode` | No |
| Raster step fails | `ERROR` | `raster_step_failed` | No |
| `shots_per_step` is invalid | `ERROR` | `invalid_value` | No |

### `CHECK_VALUE`

The accepted connections are:

- `laser_raster_x_coord`
- `laser_raster_y_coord`
- `laser_raster_x_coord_monitor`
- `laser_raster_y_coord_monitor`

The reply uses the cached target-coordinate frame. It never substitutes a motor-only cache value.

Before the first target-position read, the server returns retryable `UNKNOWN_CONNECTION/position_not_initialized`.

## PUB-SUB monitoring

PUB-SUB messages are UTF-8 text. A value message has this form:

```text
topic value
```

A heartbeat contains only this text:

```text
heartbeat
```

There is no JSON PUB payload in the current implementation.

### Server topics

| Server | Topic | Value | Approximate rate |
|---|---|---|---|
| LaserLockGUI | `heartbeat` | None | 10 Hz |
| LaserLockGUI | `1` through `8` | Wavemeter display frequency, or `0.0` | 10 Hz |
| BigSkyLasers | `heartbeat` | None | 1 Hz |
| BigSkyLasers | `<laser>_<parameter>_monitor` | Numeric controller value | 4 Hz |
| RasteringGUI | `heartbeat` | None | 1 Hz |
| RasteringGUI | `laser_raster_x_coord_monitor` | Cached target X | 4 Hz |
| RasteringGUI | `laser_raster_y_coord_monitor` | Cached target Y | 4 Hz |
| RasteringGUI | `raster_mode` | `idle`, `continuous`, `manual`, or `step` | 1 Hz |
| RasteringGUI | `raster_owner` | `local`, `remote`, or `none` | 1 Hz |
| RasteringGUI | `calibration_status` | `calibrated` or `uncalibrated` | 1 Hz |
| RasteringGUI | `raster_progress` | Step and total text | 1 Hz |

BigSky publishes `temperature`, `voltage`, `lamps`, `shutter`, and `qswitch` monitor parameters.

BigSky omits monitor messages for a disconnected laser.

RasteringGUI omits position messages until a target-coordinate cache exists.

### BLACS monitor behavior

The BLACS tab marks PUB-SUB connected after the first exact `heartbeat` message.

It marks PUB-SUB disconnected after five seconds without a heartbeat. It waits two seconds before a new subscription attempt.

The data subscriber starts after the first heartbeat. It splits each value message at the first space.

The base monitor path accepts numeric values only. It forwards them to the worker cache for shot snapshots.

Raster status topics use a separate tab callback. This path accepts their text values.

## Compatibility and client policy

Protocol v2 has no wire fallback to protocol v1.

A v2 server rejects a missing or different version with `v1_protocol_refused`.

The BLACS client rejects a reply whose `v` field is missing or is not `2`. It reports `protocol_version_mismatch` locally.

The client reports invalid reply JSON as local `malformed_reply`.

A transport timeout or transport error returns no reply. The client resets its REQ socket after that failure.

The high-level client preserves the existing worker interface for non-success replies. It returns `status`, `value: null`, `error`, and `message`.

For this local compatibility reply, `message` equals `error.message`. Current worker policy uses typed status and error fields.

The standard client timeout is five seconds. A `PROGRAM_VALUE` call with `wait_for_lock: true` uses 120 seconds.

Worker write paths raise on a missing reply or any non-`SUCCESS` status.

`check_remote_values` and `check_all_remote_values` log and skip failed reads. They also skip `SUCCESS` replies without a value.

`check_status` raises on a non-`SUCCESS` reply. It skips a `SUCCESS` reply without a value.

## Verification

Run the parent protocol and worker tests in the labscript environment:

```powershell
python -m pytest userlib/external_gui_lib/tests/test_zmq_v2.py `
  userlib/user_devices/RemoteControl/tests/test_worker_typed_status.py `
  userlib/user_devices/RemoteControl/tests/test_reply_version_gate.py -q
```

Run each server suite in its GUI environment:

```powershell
python -m pytest GUIs/BigSkyControl/tests/test_zmq_v2_protocol.py `
  GUIs/BigSkyControl/tests/test_zmq_server.py -q

python -m pytest GUIs/HF_Locking/tests/test_zmq_v2_protocol.py -q

python -m pytest GUIs/rastering/tests/test_zmq_v2_protocol.py -q
```

These tests use in-memory transports for REQ-REP behavior. They do not require bound ZMQ ports.
