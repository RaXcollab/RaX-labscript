# RaX Lab — Labscript Suite

## Repository Structure

This is a **multi-repo workspace**. The parent directory (`labscript-suite/`) is the main user-facing git repo. Several subdirectories are **separate git repos** with their own remotes:

| Directory | Remote | Role |
|---|---|---|
| `.` (labscript-suite) | `github.com/RaXcollab/RaX-labscript` | **User-facing.** Tracks `userlib/` — custom devices, sequences, analysis, connection tables. |
| `blacs/` | `github.com/shafinulh/blacs` | **Backend.** BLACS runtime: state machine, device base classes, queue manager. |
| `labscript-devices/` | `github.com/shafinulh/labscript-devices` | **Backend.** Official device drivers (PrawnBlaster, NI_DAQmx, etc.) |
| `labscript-utils/` | `github.com/shafinulh/labscript-utils` | **Backend.** Shared utilities. |

The parent repo's `.gitignore` excludes the backend folders (`blacs/`, `labscript-devices/`, `labscript-utils/`, `app_saved_configs/`, `labconfig/`, `logs/`). **Commit to each repo separately.** Do not push without asking.

### Key Paths

```
userlib/
  user_devices/          ← Custom BLACS device classes (RemoteControl, NI_SCOPE, NuvuCamera, edge_counter)
  labscriptlib/          ← Experiment sequences, connection tables, globals
  analysislib/           ← Lyse analysis scripts + utility libraries
    Main_Experiment/     ← Active analysis: analysis.py (single-shot), filtering.py, NI_SCOPE.py, Abs_data.py
logs/
  BLACS.log              ← Main BLACS log
  BLACS_faulthandler.log ← C-level crash traces (segfaults)
labconfig/
  {COMPUTER_NAME}.ini    ← Per-machine config (apparatus name, paths, etc.)
```

## Python Environment

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript
```

- Python 3.11, pyzmq=23.2.0 (do NOT upgrade pyzmq), numpy=1.26.4
- Backend repos are developer-installed: `pip install --no-build-isolation --no-deps -e blacs -e labscript-devices -e labscript-utils`

## Critical Conventions

### Qt Thread Safety in BLACS

**`@define_state` methods resume after `yield` in the mainloop BACKGROUND thread, not the Qt GUI thread.** This means:

- **USE `inmain()`** to call Qt widget methods (setValue, setText, show, hide, setEnabled, etc.)
- **DO NOT USE `with qtlock:`** for widget calls — it only pauses the Python-level event loop, does NOT marshal to the GUI thread. On Windows this causes access violations (segfaults).
- The upstream base class (`blacs/blacs/device_base_class.py:485-490`) explicitly uses `inmain()` with a comment explaining why.
- PUB-SUB daemon threads should use Qt signals (`pyqtSignal`) to communicate with the GUI thread, not direct widget calls.

### Worker Paths

Custom devices in `userlib/user_devices/` must use worker paths like:
```python
"user_devices.RemoteControl.blacs_workers.RemoteControlWorker"
```
NOT `"labscript_devices.RemoteControl..."` — that points to the wrong (or nonexistent) module.

### ExternalSoftware / RemoteControl Pattern

The `RemoteControl` device class (under `userlib/user_devices/RemoteControl/`) provides a template for interfacing BLACS with external programs (laser lock GUI, rastering GUI, etc.) via ZMQ:

- **REQ-REP** (synchronous): BLACS sends requests (PROGRAM_VALUE, CHECK_VALUE), external server responds. Used for setpoint control, manual programming, and buffered shot programming.
- **PUB-SUB** (asynchronous): External server publishes monitor values, BLACS subscribes. Used for real-time feedback (laser frequency, motor positions). ~300-500ms latency, fine for human monitoring.

Each device has 3 classes:
1. `labscript_devices.py` — Connection table API (`RemoteControl`, `RemoteAnalogOut`, `RemoteAnalogMonitor`)
2. `blacs_tabs.py` — BLACS GUI tab (`RemoteControlTab`)
3. `blacs_workers.py` — Worker process (`RemoteControlWorker`, `RemoteCommunication`)

For the full protocol spec, see `userlib/user_devices/BLACS_COMMUNICATION_CONTRACT.md`. For a worked example of subclassing this pattern, see `userlib/user_devices/RasteringDevice/` and its `BLACS_Integration_Notes.md`. For the step-by-step integration workflow, see "Workflow: Adding a New External GUI Integration" below.

### External GUI Registry

| Name | BLACS Device Class | GUI Codebase | REQ-REP Port | PUB-SUB Port | Connection Table Name |
|------|-------------------|--------------|-------------|-------------|----------------------|
| Laser Lock | `RemoteControl` | LabVIEW (not in git) | 3796 | 3797 | `LaserLockGUI` |
| Rastering GUI | `RasteringDevice` | `C:\Users\radmo\Desktop\GUIs\rastering` | 55535 | 55536 | `RasteringGUI` |

When adding a new external GUI, add it to this table.

### Workflow: Adding a New External GUI Integration

**Prerequisite:** The external GUI must have (or be given) a ZMQ REP server that speaks the JSON protocol defined in `BLACS_COMMUNICATION_CONTRACT.md`.

1. **Decide: subclass or use directly.** If the new GUI only needs setpoint control + monitors (like laser lock), use `RemoteControl` directly — no new device class needed. If it needs custom behavior (raster stepping, arm/disarm), subclass `RemoteControl`.
2. **Check the external GUI folder for `.claude/agents/`** — if a local agent exists, use it for domain-specific questions about the GUI's internals. Use `labscript-amo-expert` for BLACS-side architecture. Point the external agent to `BLACS_COMMUNICATION_CONTRACT.md` so it understands the protocol.
3. **External GUI side:** Add ZMQ server handling `HELLO`, `PROGRAM_VALUE`, `CHECK_VALUE`. Optionally add PUB-SUB with heartbeat. See the contract doc for the full spec.
4. **Create device class (if subclassing):** 5 files in `userlib/user_devices/{DeviceName}/`: `__init__.py`, `labscript_devices.py`, `register_classes.py`, `blacs_tabs.py`, `blacs_workers.py`.
5. **Connection table entry:** Import, instantiate with host/ports, add `RemoteAnalogOut` + `RemoteAnalogMonitor` children.
6. **Test:** Start external GUI first, then BLACS. Verify REQ-REP (spinbox sync), PUB-SUB (heartbeat + monitors), and buffered mode.
7. **Update this file:** Add the new GUI to the External GUI Registry table above.

**Worked examples:** `RemoteControl` (generic, laser lock) | `RasteringDevice` (subclassed, raster stepping + status indicators)

### Analysis Utilities

The analysis utility library in `userlib/analysislib/Main_Experiment/` provides reusable functions for lyse scripts and Jupyter notebooks:

- **`filtering.py`**: `process_trace()` (adaptive drift correction with slope check), `smooth()`, `butter_lowpass_filter()`
- **`NI_SCOPE.py`**: `plot_ni_scope_channels()`, `load_ni_scope_sequences()`, `ensure_time_ms()`
- **`Abs_data.py`**: `load_sequence()` (threaded batch loader), `extract_metadata()`

For analysis-specific questions, use the `lyse-analysis` agent. It knows the full utility API and the two analysis contexts: real-time lyse scripts (performance-critical) and offline Jupyter notebooks (thoroughness).

### Session Documentation

The `session-notes` agent produces structured documentation during and after work sessions. It operates in two modes:

1. **Active note-taking** — launched early in a session, resumed at milestones to log decisions, bugs, patterns, and changes into `.claude/session-scratch.md` (transient, not committed)
2. **Wrap-up** — compiles scratch notes + git diffs into three deliverables: commit message, HTML lab note (for OneNote), and CLAUDE.md/agent prompt updates

Invoke with: "start taking notes" (early) or "wrap up this session" (end). The agent drafts all artifacts and asks for confirmation before writing.

**Lab note storage convention:**

| Changes in... | Note goes in... |
|---|---|
| `userlib/analysislib/` | `userlib/analysislib/` |
| `userlib/user_devices/{Device}/` | That device folder |
| `.claude/agents/`, `CLAUDE.md` | `userlib/user_devices/` |
| Sub-repo (`blacs/`, `labscript-devices/`) | Sub-repo root |
| Cross-cutting | `userlib/` root or most impacted area |

Existing lab notes: `Analysis_Cleanup_Notes.html`, `BLACS_Integration_Notes.html`, `Agent_Configuration_Notes.html`.

### State Machine Event Ordering

Events queued by `@define_state` methods execute in FIFO order in the mainloop thread. The base class `DeviceTab.__init__` runs: `initialise_GUI()` → `restore_save_data()` → `initialise_workers()` → `program_device()`. Events queued during `initialise_workers` (like `connect_to_reqrep`) execute before `program_device`.

## Reference Documentation

- `Labscript-Confluence-2026-02-11.pdf` in repo root — Lab-specific Confluence docs covering installation, connection tables, ExternalSoftware communication, debugging notes.
- Official labscript docs: https://docs.labscriptsuite.org/
