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

**RunManager globals:** Variables like `tYAG`, `tstart`, `tend`, `DOUBLE_YAG` in sequence files are NOT undefined — they are RunManager globals injected from `.h5` globals files at compile time. This is standard labscript behavior. Do not flag them as bugs. The active globals file is `Globals/BaF_globals.h5`.

**Multiple sequences:** RunManager only compiles the selected file. Old-hardware sequences in the directory cause no issues and serve as reference for past experiments. Do not archive or delete them.

**Evolving configuration:** The connection table and sequences change as the experiment progresses (new devices, different laser configurations, new measurement modes). Treat the current state as a snapshot — do not assume device counts or channel names are fixed. Use the `amo-expert` agent for connection table questions.

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
| Laser Lock | `LaserLockDevice` | LabVIEW (not in git) | 3796 | 3797 | `LaserLockGUI` |
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

**API stability rule:** Analysis utility functions (`filtering.py`, `NI_SCOPE.py`, `Abs_data.py`, and any future utility modules) must maintain backward compatibility. New features add new kwargs with defaults; existing parameters never change meaning or get removed. This ensures old notebooks that import from these modules continue to work. New notebooks should import from the utility library rather than redefining functions inline.

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

### BLACS Saved-State Resilience

When the connection table changes (e.g., devices added/removed, parameters changed), BLACS handles stale saved state gracefully. `FrontPanelSettings.check_row()` silently excludes channels no longer in the connection table. **No need to delete the saved state h5 file** after connection table changes.

### State Machine Event Ordering

Events queued by `@define_state` methods execute in FIFO order in the mainloop thread. The base class `DeviceTab.__init__` runs: `initialise_GUI()` → `restore_save_data()` → `initialise_workers()` → `program_device()`. Events queued during `initialise_workers` (like `connect_to_reqrep`) execute before `program_device`.

### BLACS Device Patterns (RemoteControl Subclasses)

These patterns address friction points in the BLACS base class that affect any RemoteControl-pattern device with ordering constraints or non-spinbox UI. See `notes/2026-02-22_BigSky_tab_redesign.html` for the full writeup.

**Problem 1: `program_manual` sends ALL values, not deltas.** The base class calls `get_front_panel_values()` on every change, then sends the full dict to the worker. For devices where re-sending an unchanged value has side effects (e.g., BigSky rejects mode changes while lamps are active), this causes silent failures.

**Pattern: `_last_sent_values` delta tracking (worker-side)**
```python
def init(self):
    super().init()
    self._last_sent_values = {}

def check_remote_values(self):
    # ... get remote_values ...
    self._last_sent_values.update(remote_values)  # seed from remote state
    return remote_values

def program_manual(self, front_panel_values):
    for connection, value in front_panel_values.items():
        if self._last_sent_values.get(connection) == value:
            continue  # skip unchanged
        # ... send value ...
        self._last_sent_values[connection] = value
```

**Problem 2: `check_remote_values` poll races with user input.** The 5s periodic poll returns stale values and overwrites AO objects via `_update_ao_widgets`. With spinboxes this is a brief flicker; with toggle buttons the revert is very visible and can cause the reverted value to be programmed to hardware.

**Pattern: `_recently_changed` cooldown (tab-side)**
```python
self._recently_changed = {}  # {connection: monotonic_timestamp}

def _on_toggle_clicked(self, connection, value):
    self._recently_changed[connection] = time.monotonic()
    self._AO[connection].set_value(value, program=True)

def _update_ao_widgets(self, connection, value):
    if time.monotonic() - self._recently_changed.get(connection, 0) < 10:
        return  # skip — user changed this recently, poll hasn't caught up
    # ... update widget ...
```
Set the cooldown to 2x the poll interval (default 5s → 10s cooldown).

**Problem 3: `transition_to_buffered` uses safe ordering, `program_manual` does not.** If your device has command ordering constraints (e.g., must be in standby before changing mode), implement ordering in `program_manual` or the worker, not just in `transition_to_buffered`.

**Custom `initialise_GUI` pattern:** Call `create_analog_outputs()` for ALL channels (BLACS needs AO objects for save/restore and `program_device`). Create standard widgets only for continuous values. Binary controls → toggle buttons. Mode selectors → combo boxes. Command-only channels → hidden (no widget). Custom widgets call `AO.set_value(value, program=True)`.

## Reference Documentation

- `Labscript-Confluence-2026-02-11.pdf` in repo root — Lab-specific Confluence docs covering installation, connection tables, ExternalSoftware communication, debugging notes.
- Official labscript docs: https://docs.labscriptsuite.org/
