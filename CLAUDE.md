# RaX Lab — Labscript Suite

## Context Management

**When compacting**, always preserve: the file-to-agent routing table, conda activation command, External GUI Registry, "Do NOT Flag These" list, and worker path convention.

**Between unrelated tasks**, use `/clear` to reset context. Long sessions with mixed domains (BLACS debugging → sequence editing → analysis) degrade performance as irrelevant context accumulates. Use `/rename` to give sessions descriptive names for easy resumption.

**Always present results to the user before acting on them.** When an agent returns findings, proposed changes, or deliverables — present them to the user for review before committing, editing, or taking irreversible actions. This applies to all agents (wrap-up introspection, device-builder scaffolding, blacs-expert diagnoses, etc.) and to Claude itself. The user must have the opportunity to review, approve, or redirect before changes land. Never skip this step to save time.

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

**Connection table convention:** BLACS loads only the file named `connection_table.py`. Other connection table files (e.g. `connection_table_closed_cell.py`) are storage/backups and are not active.

**Connection table import pattern:** The connection table wraps all device instantiation in a `def connection_table():` function. Sequences import and call it:
```python
from labscriptlib.Main_Experiment.connection_table import connection_table
connection_table()  # re-runs device constructors every compile
```
The `if __name__ == '__main__':` guard calls `connection_table()` + `start()` + `stop()` for BLACS. **Why a function, not module-level code:** RunManager's `batch_compiler` caches modules in `sys.modules` across compiles. Module-level device instantiation only runs on the first import; after `compiler.reset()` clears `builtins` between compiles, subsequent imports are no-ops and devices vanish (`No toplevel devices and no master pseudoclock found`). The function pattern ensures device constructors re-run every compile. Device names (e.g. `YAG1_line`) are accessible via `builtins.__dict__` — no need to return them.

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

**Every Python command must be preceded by conda activation.** Bare `python` gives the wrong version (3.13 base env); `python3` hits the Windows Store shim. Always use:

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python ...
```

- Python 3.11, pyzmq=23.2.0 (do NOT upgrade pyzmq), numpy=1.26.4
- Backend repos are developer-installed: `pip install --no-build-isolation --no-deps -e blacs -e labscript-devices -e labscript-utils`

## Critical Conventions

### File Move/Delete Safety

**NEVER run `rm -rf`, `rm -r`, `mv` on directories, or any destructive file operations without explicit user confirmation first.** Always show the exact command and wait for approval. For diagnostic checks, use read-only commands (`ls`, `stat`, `test -d`, `du`) — never `mv` or `rm`. This rule exists because a botched `mv` during a directory migration destroyed unpushed git commits (recovered from Windows File History).

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
| Laser Lock | `LaserLockDevice` | `C:\Users\radmo\Desktop\GUIs\HF_Locking` | 3796 | 3797 | `LaserLockGUI` |
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

**Worked examples:** `RemoteControl` (generic, laser lock) | `RasteringDevice` (subclassed, raster stepping + status indicators) | `BigSkyHub` (subclassed, safe command ordering + auto-created children + serial disconnect resilience)

### Analysis Utilities

@docs/analysis-api.md

### NI_SCOPE Data Conventions

@docs/ni-scope-conventions.md

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
| Codebase audit / code review | Domain agents per routing table below | Use `blacs-expert` for user_devices/blacs/, `amo-expert` for labscriptlib/, `lyse-analysis` for analysislib/. **Never** use generic Explore for audits — it produces false positives on physics-lab conventions (RunManager globals, thread safety patterns, device registration). |

**File-to-agent routing:** When searching or auditing files, validate findings through the domain agent that owns that path. Generic Explore agents lack physics-lab context and produce false positives.

| Path pattern | Route to | Why |
|---|---|---|
| `labscriptlib/` (sequences, connection tables, globals) | `amo-expert` | RunManager globals, device config semantics |
| `analysislib/` (analysis scripts, notebooks) | `lyse-analysis` | API stability, utility library conventions |
| `user_devices/` (BLACS device classes) | `device-builder` (confers with `blacs-expert` + `amo-expert`) | Thread safety, state machine, ZMQ protocol, connection table fit |
| `blacs/` (BLACS runtime, base classes) | `blacs-expert` | State machine, Qt threading, base class behavior |
| `labscript-devices/` (official device drivers) | `blacs-expert` | Device driver internals, NI_DAQmx patterns |
| `labscript-utils/` (shared utilities) | `blacs-expert` | Utility internals, h5_lock, properties |
| `logs/` (BLACS.log, faulthandler) | `labscript-diagnostics` | Log parsing, recurrence analysis |
| `notes/` (lab notes, session history) | `labscript-diagnostics` | Correlate errors with recent changes |
| External GUI codebases | Local agent in `.claude/agents/` of the GUI directory | GUI internals, motor control, ZMQ server |

**External GUI agent discovery:** Check for `.claude/agents/` inside the GUI's codebase directory (e.g., `C:\Users\radmo\Desktop\GUIs\rastering\.claude\agents\ablation-tech.md`). The External GUI Registry above lists each GUI's codebase path.

### Do NOT Flag These

These are normal in this codebase — not bugs, not code smell, not cleanup opportunities:

- **RunManager globals** (`tYAG`, `tstart`, `DOUBLE_YAG`, etc.) appearing "undefined" in sequence files — they are injected at compile time
- **`__pycache__/` and `.ipynb_checkpoints/` directories** — auto-managed by Python and Jupyter
- **Single-occurrence log errors** without recurrence — flag as yellow observation, not critical (check frequency before escalating)
- **Connection table parameters that differ from hardware maximums** — they reflect the current experiment, not hardware limits (e.g., `num_lasers=1` when 2 are wired)
- **Inline function definitions in old Jupyter notebooks** — frozen analysis snapshots, not code duplication
- **NaN rows in NI_SCOPE h5 datasets** — unsaved channels are NaN-filled intentionally (selective saving), not data corruption
- **Deprecated kwargs in analysis utilities** — `beforeYAG_time`, `after_abs_time`, `end_time` in `process_trace()` are backward-compat aliases, not dead code

### Agent Workflow (plan agent use upfront, not as afterthoughts)

During the planning phase, walk through the full agent pipeline from start to finish:

1. **Plan phase:** Identify which domain agents to consult (routing table above), include `session-notes` for tracking, and include `wrap-up` for deliverables — all in the plan itself.
2. **Implementation phase:** Execute with domain agents. `session-notes` runs in background.
3. **Deliverables phase:** `wrap-up` agent runs its fixed pipeline (diffs → commits → lab note → introspection → context updates).

The Deliverables section of every plan must specify which agents produce which artifacts, so nothing is forgotten.

**session-notes:** At session start, ask the user if they want session-notes tracking (use AskUserQuestion, short yes/no). If yes, launch in background and resume at milestones. `session-notes` handles note-taking only — wrap-up deliverables are owned by the `wrap-up` agent. For pure config/tooling sessions (editing CLAUDE.md, agent prompts, settings, skills) where changes are self-documenting, session-notes can be skipped — the diffs serve as the record.

**Plan mode integration:** Use specialized agents (`device-builder`, `blacs-expert`, `amo-expert`) as your Explore/Plan agents for domain-matching tasks. Don't default to generic Explore/Plan when a specialized agent exists.

**Routing enforcement (check before every agent launch):** Before launching any Explore or Plan agent, check the file-to-agent routing table above. If the task touches files owned by a domain agent, use that domain agent instead. This applies to plan mode Phase 1 (exploration) and Phase 2 (design) — both should use domain agents for domain-matching paths. The routing table is authoritative; generic agents are a last resort for truly cross-cutting or novel tasks.

**Small fixes (single-file, ~10 lines, obvious approach):** Don't use full multi-phase plan mode. Instead, state the fix in a few sentences, then ask the user for permission to proceed. One cycle, not three.

**Full plan mode:** Multi-file changes, architectural decisions, unclear requirements, or anything the user explicitly requests planning for.

**Standard deliverables checklist** (owned by `wrap-up` agent):
1. Commit(s) — to correct repo(s)
2. HTML lab note — `notes/YYYY-MM-DD_Topic.html`
3. Session introspection — what went well, what to improve, lessons
4. CLAUDE.md / agent prompt updates — if conventions changed

### BLACS Saved-State Resilience

When the connection table changes (e.g., devices added/removed, parameters changed), BLACS handles stale saved state gracefully. `FrontPanelSettings.check_row()` silently excludes channels no longer in the connection table. **No need to delete the saved state h5 file** after connection table changes.

### State Machine Event Ordering

Events queued by `@define_state` methods execute in FIFO order in the mainloop thread. The base class `DeviceTab.__init__` runs: `initialise_GUI()` → `restore_save_data()` → `initialise_workers()` → `program_device()`. Events queued during `initialise_workers` (like `connect_to_reqrep`) execute before `program_device`.

### BLACS Device Patterns (RemoteControl Subclasses)

@docs/blacs-device-patterns.md

## Reference Documentation

- `Labscript-Confluence-2026-02-11.pdf` in repo root — Lab-specific Confluence docs covering installation, connection tables, ExternalSoftware communication, debugging notes.
- Official labscript docs: https://docs.labscriptsuite.org/
