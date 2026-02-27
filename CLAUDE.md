# RaX Lab — Labscript Suite

## Context Management

- **When compacting**, always preserve: Available Tools section, conda activation command, External GUI Registry, "Do NOT Flag These" list, and `.claude/rules/` pointer.
- **Between unrelated tasks**, use `/clear` to reset context. Mixed domains degrade performance.
- **Always present results before acting.** Agent findings and deliverables must be reviewed before committing or taking irreversible actions.

## Repository Structure

**Multi-repo workspace.** Parent is the main git repo. Subdirectories are separate repos:

| Directory | Remote | Role |
|---|---|---|
| `.` (labscript-suite) | `github.com/RaXcollab/RaX-labscript` | **User-facing.** Tracks `userlib/` — custom devices, sequences, analysis. |
| `blacs/` | `github.com/shafinulh/blacs` | **Backend.** BLACS runtime, state machine, device base classes. |
| `labscript-devices/` | `github.com/shafinulh/labscript-devices` | **Backend.** Official device drivers (PrawnBlaster, NI_DAQmx, etc.) |
| `labscript-utils/` | `github.com/shafinulh/labscript-utils` | **Backend.** Shared utilities. |

- Parent `.gitignore` excludes backend folders (`blacs/`, `labscript-devices/`, `labscript-utils/`, `app_saved_configs/`, `labconfig/`, `logs/`, `GUIs/`)
- **Commit to each repo separately.** Do not push without asking.
- This machine runs `Main_Experiment` — only `userlib/labscriptlib/Main_Experiment/` is relevant
- Domain rules (Qt safety, worker paths, RunManager globals, analysis) in `.claude/rules/` — auto-load per file path

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

- Shot h5 files: `C:\Users\radmo\MIT Dropbox\Shungo Fukaya\Experiments\Main_Experiment\`
- Configured in `labconfig/RaX-Control.ini` as `experiment_shot_storage`
- Organized by `YYYY/MM/DD/`

## Python Environment

- **Every Python command needs conda activation.** Bare `python` → wrong version; `python3` → Windows Store shim.

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python ...
```

- Python 3.11, pyzmq=23.2.0 (do NOT upgrade pyzmq), numpy=1.26.4
- Backend repos: `pip install --no-build-isolation --no-deps -e blacs -e labscript-devices -e labscript-utils`

## Critical Conventions

### File Move/Delete Safety

- **NEVER** `rm -rf`, `rm -r`, `mv` on directories without explicit user confirmation
- Use read-only commands (`ls`, `stat`, `test -d`) for diagnostics — never `mv` or `rm`

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

Add new external GUIs to this table.

## Do NOT Flag These

- **`__pycache__/` and `.ipynb_checkpoints/`** — auto-managed by Python and Jupyter
- **Single-occurrence log errors** without recurrence — yellow observation, not critical
- Domain-specific suppressions (RunManager globals, NaN rows, deprecated kwargs) in `.claude/rules/`

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
