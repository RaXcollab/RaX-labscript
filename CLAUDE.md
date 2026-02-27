# RaX Lab — Labscript Suite

## Context Management

- **When compacting**, always preserve: Available Tools section, conda activation command, External GUI Registry, "Do NOT Flag These" list, and worker path convention.
- **Between unrelated tasks**, use `/clear` to reset context. Mixed domains (BLACS debugging → sequence editing → analysis) degrade performance.
- **Always present results to the user before acting on them.** When an agent returns findings or deliverables, present for review before committing, editing, or taking irreversible actions. Never skip this step.

## Repository Structure

This is a **multi-repo workspace**. The parent directory is the main user-facing git repo. Subdirectories are separate git repos:

| Directory | Remote | Role |
|---|---|---|
| `.` (labscript-suite) | `github.com/RaXcollab/RaX-labscript` | **User-facing.** Tracks `userlib/` — custom devices, sequences, analysis. |
| `blacs/` | `github.com/shafinulh/blacs` | **Backend.** BLACS runtime, state machine, device base classes. |
| `labscript-devices/` | `github.com/shafinulh/labscript-devices` | **Backend.** Official device drivers (PrawnBlaster, NI_DAQmx, etc.) |
| `labscript-utils/` | `github.com/shafinulh/labscript-utils` | **Backend.** Shared utilities. |

The parent `.gitignore` excludes backend folders (`blacs/`, `labscript-devices/`, `labscript-utils/`, `app_saved_configs/`, `labconfig/`, `logs/`, `GUIs/`). **Commit to each repo separately.** Do not push without asking.

### This PC: Main_Experiment

- Only `userlib/labscriptlib/Main_Experiment/` is relevant — ignore `lyman29/` and other folders
- BLACS loads only `connection_table.py` — other connection table files are backups
- **Connection table import pattern:** Device instantiation wrapped in `def connection_table():` function, not module-level. Sequences call `from labscriptlib.Main_Experiment.connection_table import connection_table; connection_table()`. This is required because `sys.modules` caching + `compiler.reset()` between compiles.
- **RunManager globals** (`tYAG`, `tstart`, `DOUBLE_YAG`, etc.) are injected at compile time from `Globals/BaF_globals.h5` — not undefined variables
- Old sequences in the directory are reference for past experiments — don't archive or delete
- Configuration evolves with the experiment — don't assume device counts or channel names are fixed

### Key Paths

```
userlib/
  user_devices/          ← Custom BLACS device classes (RemoteControl, NI_SCOPE, NuvuCamera, edge_counter)
  labscriptlib/
    Main_Experiment/     ← THIS PC's sequences, connection tables, globals
  analysislib/
    Main_Experiment/     ← Active analysis: analysis.py, filtering.py, NI_SCOPE.py, Abs_data.py
logs/
  BLACS.log              ← Main BLACS log
  BLACS_faulthandler.log ← C-level crash traces (segfaults)
labconfig/
  {COMPUTER_NAME}.ini    ← Per-machine config (apparatus name, paths, etc.)
```

### Experiment Data Storage

Shot h5 files are stored on Dropbox (synced across lab machines):
```
C:\Users\radmo\MIT Dropbox\Shungo Fukaya\Experiments\Main_Experiment\
```
Configured in `labconfig/RaX-Control.ini` as `experiment_shot_storage`. Organized by `YYYY/MM/DD/`.

## Python Environment

**Every Python command must be preceded by conda activation.** Bare `python` → wrong version (3.13); `python3` → Windows Store shim.

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python ...
```

- Python 3.11, pyzmq=23.2.0 (do NOT upgrade pyzmq), numpy=1.26.4
- Backend repos: `pip install --no-build-isolation --no-deps -e blacs -e labscript-devices -e labscript-utils`

## Critical Conventions

### File Move/Delete Safety

- **NEVER** `rm -rf`, `rm -r`, `mv` on directories without explicit user confirmation
- Use read-only commands (`ls`, `stat`, `test -d`) for diagnostics — never `mv` or `rm`

### Qt Thread Safety in BLACS

- `@define_state` methods resume after `yield` in the mainloop BACKGROUND thread, not the Qt GUI thread
- **USE `inmain()`** for Qt widget calls (setValue, setText, show, hide, setEnabled, etc.)
- **DO NOT USE `with qtlock:`** — it doesn't marshal to the GUI thread; causes Windows access violations
- PUB-SUB daemon threads → use `pyqtSignal` to bridge to the GUI thread

### Worker Paths

- Custom devices: `"user_devices.RemoteControl.blacs_workers.RemoteControlWorker"`
- NOT `"labscript_devices.RemoteControl..."` — wrong module

### Verification

- **Sequence changes**: compile in RunManager → check for errors
- **Connection table changes**: compile + restart BLACS
- **Device class changes**: restart BLACS, check `logs/BLACS.log`
- **Analysis changes**: re-run lyse single-shot script on a recent h5
- **External GUI changes**: restart the GUI, verify ZMQ with `/check-guis`
- **After any BLACS change**: run a test shot, check h5 output in HDFView
- **Connection table property changes**: recompile → BLACS auto-loads new properties (no need to delete saved state)

## External GUI Registry

| Name | BLACS Device Class | GUI Codebase | REQ-REP Port | PUB-SUB Port | Connection Table Name |
|------|-------------------|--------------|-------------|-------------|----------------------|
| Laser Lock | `LaserLockDevice` | `GUIs\HF_Locking` | 3796 | 3797 | `LaserLockGUI` |
| Rastering GUI | `RasteringDevice` | `GUIs\rastering` | 55535 | 55536 | `RasteringGUI` |
| BigSky YAG Hub | `BigSkyHub` | `GUIs\BigSkyControl` | 55540 | 55541 | `BigSkyLasers` |

When adding a new external GUI, add it to this table.

## Do NOT Flag These

These are normal in this codebase — not bugs, not code smell, not cleanup opportunities:

- **RunManager globals** (`tYAG`, `tstart`, `DOUBLE_YAG`, etc.) appearing "undefined" in sequences — injected at compile time
- **`__pycache__/` and `.ipynb_checkpoints/`** — auto-managed by Python and Jupyter
- **Single-occurrence log errors** without recurrence — flag as yellow observation, not critical
- **Connection table parameters that differ from hardware maximums** — reflect current experiment, not hardware limits
- **Inline function definitions in old Jupyter notebooks** — frozen analysis snapshots
- **NaN rows in NI_SCOPE h5 datasets** — unsaved channels are NaN-filled intentionally (selective saving)
- **Deprecated kwargs in analysis utilities** — `beforeYAG_time`, `after_abs_time`, `end_time` are backward-compat aliases

## Available Tools

### Skills (auto-activate or invoke with /name)

- `/check-sequence` — validate sequence globals, devices, structure before compilation
- `/check-guis` — ping ZMQ ports to verify external GUIs are running
- `/debug-blacs` — standardized BLACS triage workflow (logs → routing → diagnosis)
- `/new-device` — scaffold a new external GUI BLACS integration (5-file pattern)

### Agents (launched automatically based on task type)

- `blacs-expert` — Qt threading, state machine, BLACS runtime internals
- `amo-expert` — sequences, connection tables, experiment design, RunManager
- `device-builder` — scaffolding new device classes (confers with blacs-expert + amo-expert)
- `lyse-analysis` — analysis scripts, Jupyter notebooks, utility API
- `labscript-diagnostics` — log parsing, error diagnosis, recurrence analysis
- `session-notes` — background note-taking during sessions (sonnet, lightweight)
- `wrap-up` — end-of-session deliverables (commits, lab notes, introspection, context updates)
- Orchestration rules (routing table, workflow, deliverables checklist) auto-load via `agent-workflow` skill

## Reference Documentation

### Analysis Utilities

@docs/analysis-api.md

### NI_SCOPE Data Conventions

@docs/ni-scope-conventions.md

### BLACS Device Patterns (RemoteControl Subclasses)

@docs/blacs-device-patterns.md

### Other References

- `Labscript-Confluence-2026-02-11.pdf` in repo root — Lab-specific Confluence docs
- Official labscript docs: https://docs.labscriptsuite.org/
