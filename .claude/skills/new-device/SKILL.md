---
name: new-device
description: Scaffold a new external GUI integration into BLACS following the RemoteControl pattern
disable-model-invocation: true
---

Scaffold a new BLACS device integration for: $ARGUMENTS

Follow the integration checklist from CLAUDE.md:

## Step 0: Setup
- Launch `session-notes` in background to track decisions.
- Read the External GUI Registry in CLAUDE.md.

## Step 1: Assess
- Ask: Does the device need custom behavior (subclass RemoteControl) or just setpoint control + monitors (use RemoteControl directly)?
- Check the external GUI folder for `.claude/agents/` — use local agents for GUI internals.

## Step 2: External GUI Side
- Verify or add ZMQ REP server handling `HELLO`, `PROGRAM_VALUE`, `CHECK_VALUE`.
- Follow `userlib/user_devices/BLACS_COMMUNICATION_CONTRACT.md`.

## Step 3: Create Device Class
Use the `device-builder` agent to scaffold 5 files in `userlib/user_devices/$ARGUMENTS/`:
- `__init__.py`
- `labscript_devices.py`
- `blacs_tabs.py`
- `blacs_workers.py`
- `register_classes.py`

Reference implementations: `RemoteControl` (generic), `RasteringDevice` (subclassed), `BigSkyHub` (subclassed with ordering).

**Base worker IS the typed-status contract — do NOT hand-roll it.** The base `RemoteControlWorker` handles v2 replies: read/poll/snapshot paths log + skip non-SUCCESS (`_skip_non_success_read`), write paths raise (`_check_response`). Use the base worker as-is; override only for a genuine, tested specialization (e.g. BigSky buffered skip-unlaunched). Never copy BigSky's message-substring gates. See `docs/remotecontrol-zmq-protocol-v2.md` §12 and `memory/feedback_remotecontrol-base-is-the-contract.md`.

## Step 4: Connection Table
Add import and instantiation to `userlib/labscriptlib/Main_Experiment/connection_table.py`.
Prefer auto-created children in `__init__` (BigSkyHub pattern).

## Step 5: Test
1. Start external GUI
2. Start BLACS
3. Verify REQ-REP connection (tab should show connected)
4. Verify PUB-SUB monitoring (if applicable)
5. Use `labscript-diagnostics` if errors appear

## Step 6: Update Registry
Add the new GUI to the External GUI Registry table in CLAUDE.md.

## Step 7: Wrap Up
Launch `wrap-up` agent for commit, lab note, and context updates.
