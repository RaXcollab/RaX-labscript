# BLACS Communication Contract for External GUIs — v1 (DEPRECATED 2026-05-23)

> **STATUS**: **v1 is dead code after the v2 cutover lands**. The wire-
> format examples below describe the OLD protocol. New client/server
> code MUST use v2 — see
> [`docs/remotecontrol-zmq-protocol-v2.md`](../../docs/remotecontrol-zmq-protocol-v2.md)
> (canonical spec) and
> [`docs/zmq-v2-cutover-runbook.md`](../../docs/zmq-v2-cutover-runbook.md)
> (cutover sequence). v2 servers REFUSE v1 envelopes per Q4 hard sunset.
> This doc is preserved for archaeological context of what the wire
> format used to look like.

**If you are an agent working on an external GUI that integrates with BLACS, read this document to understand the (historical) communication protocol; then read the v2 spec for the live wire format.**

This defines the (historical v1) ZMQ protocol contract between BLACS (the experiment control system) and external programs (laser lock GUIs, rastering GUIs, wavemeters, etc.).

## ZMQ REQ-REP Protocol (Synchronous)

BLACS is the **client** (ZMQ REQ socket). The external GUI is the **server** (ZMQ REP socket).

### Request format (JSON)

```json
{"action": "HELLO|PROGRAM_VALUE|CHECK_VALUE", "connection": "<string>", "value": <any>, "wait_for_lock": <bool>}
```

### Actions

**HELLO** — Connection check. BLACS sends this on startup to verify the server is alive.
- Request: `{"action": "HELLO", "connection": ""}`
- Response: `{"status": "SUCCESS"}`

**PROGRAM_VALUE** — Set a value on the remote device.
- Request: `{"action": "PROGRAM_VALUE", "connection": "<channel_name>", "value": <float>, "wait_for_lock": false}`
- Response: `{"status": "SUCCESS"}` or `{"status": "ERROR", "message": "<reason>"}`
- `wait_for_lock=true`: used during buffered shots. Server should block until the value is confirmed (e.g., motor has finished moving, laser lock has converged). Extended timeout (120s).
- `wait_for_lock=false` (default): manual mode, set-and-forget. Short timeout (5s).

**CHECK_VALUE** — Read the current value of a channel.
- Request: `{"action": "CHECK_VALUE", "connection": "<channel_name>"}`
- Response: `{"status": "SUCCESS", "connection": "<channel_name>", "value": <float>}`

**Custom actions** — Use `PROGRAM_VALUE` with a special connection name (e.g., `move_to_next` for raster stepping). The server interprets the connection name and value to decide what to do. Return status/error as usual; use additional keys (e.g., `"status": "FINISHED"`) for special states.

### Error handling

- On timeout: BLACS resets the REQ socket and retries on the next cycle. The server should not hang indefinitely.
- On error response: BLACS logs the error. During buffered shots, errors abort the shot.
- **Servers MUST return `{"status": "ERROR", "message": "..."}` for rejected commands.** Do not swallow failures by always returning SUCCESS. If a command is rejected (e.g., mode change while laser is active), return ERROR so BLACS can detect the failure. Silent SUCCESS on rejected commands causes state desync between BLACS and the remote device.

## ZMQ PUB-SUB Protocol (Asynchronous)

The external GUI is the **publisher** (ZMQ PUB socket). BLACS is the **subscriber** (ZMQ SUB socket).

### Message format

```
"{topic} {value}"
```

Space-separated string. Topic is the subscription key, value is everything after the first space. Example: `"laser_raster_x_coord_monitor 12.345"`

### Required topics

| Topic | Format | Frequency | Purpose |
|-------|--------|-----------|---------|
| `heartbeat` | `"heartbeat"` (no value) | ~1 Hz | Connection detection. BLACS subscribes to this first, then connects data subscribers on first heartbeat. |

### Monitor topics

| Topic | Format | Frequency | Purpose |
|-------|--------|-----------|---------|
| `{connection}_monitor` | `"{connection}_monitor {float}"` | ~4 Hz | Live value for display. Must match `RemoteAnalogMonitor` connection name in connection table. |

### Status topics (optional)

Custom topics for non-numeric status. Subscribe and display as needed. Examples:
- `"raster_mode step"` — current operating mode
- `"calibration_status calibrated"` — binary state
- `"raster_progress 5/20"` — progress indicator

## Connection Naming Conventions

- **Writable outputs**: descriptive name matching the physical quantity (e.g., `laser_raster_x_coord`, `tisa_1_setpoint`)
- **Read-only monitors**: same base name with `_monitor` suffix (e.g., `laser_raster_x_coord_monitor`)
- Names must match exactly between the external GUI's ZMQ server and the BLACS connection table entry
- Changing a connection name requires updating **both** the external GUI and the BLACS device

## BLACS Shot Lifecycle

When BLACS runs a shot, it calls these methods on the worker (in order):

1. **`transition_to_buffered`**: Programs values from the HDF5 shot file. May send `PROGRAM_VALUE` with `wait_for_lock=true`. Custom actions (e.g., raster stepping) also happen here.
2. **Shot executes** (hardware triggers, data acquisition)
3. **`transition_to_manual`**: Returns to manual mode. Captures final monitor values to HDF5.

Between shots (manual mode):
- **`program_manual`**: Sends `PROGRAM_VALUE` (without `wait_for_lock`) when user changes spinbox values in the BLACS tab
- **Periodic polling**: Sends `CHECK_VALUE` for each output channel (~1 Hz) to keep the BLACS display in sync

## Worked Examples

- **Client side** (BLACS): `userlib/user_devices/RemoteControl/blacs_workers.py` — `RemoteCommunication` class
- **Generic server**: Laser lock GUI (LabVIEW, not in git) — simplest case, just PROGRAM_VALUE + CHECK_VALUE
- **Extended server**: `GUIs\rastering\raster_controller.py:_zmq_loop()` — adds HELLO, PUB-SUB, custom `move_to_next` action
- **Extended BLACS device**: `userlib/user_devices/RasteringDevice/` — subclassed worker + tab with status indicators. See `BLACS_Integration_Notes.md` in that directory.

## Cross-References

- For BLACS architecture (state machines, Qt thread safety, device base classes): see the `amo-expert` agent in `C:\Users\radmo\labscript-suite\.claude\agents\`
- For the integration workflow checklist: see "Workflow: Adding a New External GUI Integration" in `C:\Users\radmo\labscript-suite\CLAUDE.md`
- For existing integrations: see the External GUI Registry in `CLAUDE.md`
