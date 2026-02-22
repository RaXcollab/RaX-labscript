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

### This PC: Main_Experiment

This machine runs the `Main_Experiment` apparatus. Only `userlib/labscriptlib/Main_Experiment/` is relevant — ignore `lyman29/` and other labscriptlib folders.

**Connection table convention:** BLACS loads only the file named `connection_table.py`. Other connection table files (e.g. `connection_table_closed_cell.py`) are storage/backups and are not active. Sequence files must duplicate the active connection table header exactly — keep them in sync when devices are added or removed.

### Key Paths

```
userlib/
  user_devices/          ← Custom BLACS device classes (RemoteControl, NI_SCOPE, NuvuCamera, edge_counter)
  labscriptlib/
    Main_Experiment/     ← THIS PC's sequences, connection tables, globals (ignore other folders)
  analysislib/
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

The `RemoteControl` device class (`userlib/user_devices/RemoteControl/`) is the template for all external program integrations via ZMQ (REQ-REP for commands, PUB-SUB for monitors). Each device has 3 classes: `labscript_devices.py`, `blacs_tabs.py`, `blacs_workers.py`. For the full protocol, see `BLACS_COMMUNICATION_CONTRACT.md`. Use the `device-builder` agent for scaffolding new devices.

### External GUI Registry

| Name | BLACS Device Class | GUI Codebase | REQ-REP Port | PUB-SUB Port | Connection Table Name |
|------|-------------------|--------------|-------------|-------------|----------------------|
| Laser Lock | `RemoteControl` | LabVIEW (not in git) | 3796 | 3797 | `LaserLockGUI` |
| Rastering GUI | `RasteringDevice` | `C:\Users\radmo\Desktop\GUIs\rastering` | 55535 | 55536 | `RasteringGUI` |
| BigSky YAG Hub | `BigSkyHub` | `C:\Users\radmo\Desktop\GUIs\BigSkyControl` | 55540 | 55541 | `BigSkyLasers` |

When adding a new external GUI, add it to this table.

### Workflow: Adding a New External GUI Integration

**Prerequisite:** The external GUI must have (or be given) a ZMQ REP server that speaks the JSON protocol defined in `BLACS_COMMUNICATION_CONTRACT.md`.

0. **Start `session-notes`** in the background to track decisions and patterns.
1. **Decide: subclass or use directly.** Setpoint control + monitors only → use `RemoteControl` directly. Custom behavior → subclass.
2. **Check the external GUI folder for `.claude/agents/`** — use local agent for GUI internals, `device-builder` for BLACS-side scaffolding.
3. **External GUI side:** Add ZMQ server handling `HELLO`, `PROGRAM_VALUE`, `CHECK_VALUE`. See `BLACS_COMMUNICATION_CONTRACT.md`.
4. **Create device class (if subclassing):** Use `device-builder` agent. 5 files in `userlib/user_devices/{DeviceName}/`.
5. **Connection table entry:** Import, instantiate. Auto-create children in `__init__` (BigSkyHub pattern, preferred) or declare manually (RasteringDevice pattern).
6. **Test:** Start external GUI → BLACS. Use `labscript-diagnostics` if errors appear in logs.
7. **Update this file:** Add the new GUI to the External GUI Registry table.
8. **Wrap up:** Resume `session-notes` for commit message, HTML lab note, context updates, and session introspection.

**Worked examples:** `RemoteControl` (generic, laser lock) | `RasteringDevice` (subclassed, raster stepping + status indicators) | `BigSkyHub` (subclassed, safe command ordering + auto-created children)

### Analysis Utilities

The analysis utility library in `userlib/analysislib/Main_Experiment/` provides reusable functions for lyse scripts and Jupyter notebooks:

- **`filtering.py`**: `process_trace()` (adaptive drift correction with slope check), `smooth()`, `butter_lowpass_filter()`
- **`NI_SCOPE.py`**: `plot_ni_scope_channels()`, `load_ni_scope_sequences()`, `ensure_time_ms()`
- **`Abs_data.py`**: `load_sequence()` (threaded batch loader), `extract_metadata()`

For analysis-specific questions, use the `lyse-analysis` agent. It knows the full utility API and the two analysis contexts: real-time lyse scripts (performance-critical) and offline Jupyter notebooks (thoroughness).

### Session Documentation

The `session-notes` agent tracks decisions and produces structured documentation. See Agent Orchestration below for when to invoke it.

**Lab notes** are stored in `notes/` with date prefixes: `YYYY-MM-DD_Topic.html`.
**Front-facing user guide:** `docs/Using_Claude_Code.html` — update when the agent system changes.

### Agent Orchestration

Invoke agents proactively based on task type. Don't wait for the user to ask.

| Task type | Agents to invoke | When |
|---|---|---|
| New device integration | `device-builder` (planning + implementation) | During plan/design/build |
| BLACS crash / thread issue | `blacs-expert` → `labscript-diagnostics` | Immediately |
| Experiment sequence design | `amo-expert` | When writing sequences or connection tables |
| Analysis work | `lyse-analysis` | When touching analysislib/ |

**session-notes:** At session start, ask the user if they want session-notes tracking (use AskUserQuestion, short yes/no). If yes, launch in background and resume at milestones. If no, skip — but still offer wrap-up deliverables at session end.

**Plan mode integration:** Use specialized agents (`device-builder`, `blacs-expert`, `amo-expert`) as your Explore/Plan agents for domain-matching tasks. Don't default to generic Explore/Plan when a specialized agent exists.

**Small fixes (single-file, ~10 lines, obvious approach):** Don't use full multi-phase plan mode. Instead, state the fix in a few sentences, then ask the user for permission to proceed. One cycle, not three.

**Full plan mode:** Multi-file changes, architectural decisions, unclear requirements, or anything the user explicitly requests planning for.

**Wrap-up deliverables:** Every plan must end with a Deliverables section (after Verification). This ensures they are planned upfront, not forgotten. Execute deliverables only after the user confirms verification passed.

Standard deliverables:
1. Commit(s) — to correct repo(s)
2. HTML lab note — `notes/YYYY-MM-DD_Topic.html`
3. CLAUDE.md updates — if conventions/registry changed
4. Session introspection — what went well, what to improve, lessons

### State Machine Event Ordering

Events queued by `@define_state` methods execute in FIFO order in the mainloop thread. The base class `DeviceTab.__init__` runs: `initialise_GUI()` → `restore_save_data()` → `initialise_workers()` → `program_device()`. Events queued during `initialise_workers` (like `connect_to_reqrep`) execute before `program_device`.

## Reference Documentation

- `Labscript-Confluence-2026-02-11.pdf` in repo root — Lab-specific Confluence docs covering installation, connection tables, ExternalSoftware communication, debugging notes.
- Official labscript docs: https://docs.labscriptsuite.org/
