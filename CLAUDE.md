# RaX Lab — Labscript Suite

## Context Management

- **When compacting**, always preserve: Available Tools section, conda activation command, External GUI Registry, "Do NOT Flag These" list, and `.claude/rules/` pointer.
- **Between unrelated tasks**, use `/clear` to reset context. Mixed domains degrade performance.
- **Always present results before acting.** Agent findings and deliverables must be reviewed before committing or taking irreversible actions.
- **Research before proposing.** During planning, proactively search for expert guidance, existing patterns, and hard constraints before designing solutions — don't wait for the user to ask.

## Repository Structure

**Multi-repo workspace.** Parent is the main git repo. Subdirectories are separate repos:

| Directory | Remote | Role |
|---|---|---|
| `.` (labscript-suite) | `github.com/RaXcollab/RaX-labscript` | **User-facing.** Tracks `userlib/` — custom devices, sequences, analysis. |
| `blacs/` | `github.com/RaXcollab/blacs` | **Backend.** BLACS runtime, state machine, device base classes. |
| `labscript-devices/` | `github.com/RaXcollab/labscript-devices` | **Backend.** Official device drivers (PrawnBlaster, NI_DAQmx, etc.) |
| `labscript-utils/` | `github.com/RaXcollab/labscript-utils` | **Backend.** Shared utilities. |

- Parent `.gitignore` excludes backend folders (`blacs/`, `labscript-devices/`, `labscript-utils/`, `app_saved_configs/`, `labconfig/`, `logs/`, `GUIs/`)
- Backend repos are **`RaXcollab/*` forks of `shafinulh/*`** (the historical upstream). `origin` points at RaXcollab over SSH (key auth as `RadMolecules`). `shafinulh/*` is no longer a configured remote — re-add as `upstream` if you need to pull upstream changes.
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

## Design Philosophy

- **Modularity over simplicity** — when the user describes distinct categories (e.g., manual vs timed vs latched channels), the solution must handle each type independently. Do NOT collapse into blanket behavior.
- **Need-driven complexity** — match solution complexity to the problem. A latched channel gets distinct code; a rename gets one line.
- **Our fork is ground truth** — `RaXcollab/blacs`, `RaXcollab/labscript-devices`, `RaXcollab/labscript-utils` (forked from `shafinulh/*`) are custom. When official docs disagree with our code, our code wins.

## Critical Conventions

### File Move/Delete Safety

- **NEVER** `rm -rf`, `rm -r`, `mv` on directories without explicit user confirmation
- Use read-only commands (`ls`, `stat`, `test -d`) for diagnostics — never `mv` or `rm`

### Lab-Wide Invariants (load-bearing)

- **Never tag backend repos (`blacs`, `labscript-devices`, `labscript-utils`) with non-`v*` tags** — setuptools_scm parses `git describe` at import time; a non-version tag reachable from HEAD crashes `import labscript_utils` → BLACS/RunManager cannot start. Pin backend baselines by commit hash (`docs/stable-snapshot-2026-06-09.md`).
- **Per-shot teardown** belongs in `post_experiment`, NOT `transition_to_manual`. The fork's queued-shot lifecycle runs `transition_to_buffered → start_run → post_experiment` per shot; `transition_to_manual` only runs at queue-end, abort, or pause. Fork-only MODE flags: `MODE_TRANSITION_TO_POST_EXP=16`, `MODE_POST_EXP=32`. Worker classes without `post_experiment` trigger a ~80 ms back-compat probe per shot.
- **HF lock spec (canonical):** lock acquires when **5** consecutive in-tolerance samples land within `LOCK_TOLERANCE = 5e-6 THz = 5 MHz`, with `LOCK_TIMEOUT_S = 60`. Code is authoritative — `GUIs/HF_Locking/workers.py:21-22`. Older "2 consecutive" notes are stale; correct everywhere on contact.
- **Authoritative scan x-axis** for RemoteControl-programmed scans is `/devices/{dev}/remote_device_operation['{ch}'][0]` (the actual labscript intent, full float64). `front_panel`, `_AO/value`, and `monitor_values` lag, quantize, or were `float32` pre-2026-04-29.

### Verification

- **Sequence changes**: compile in RunManager → check for errors
- **Connection table changes**: compile + restart BLACS
- **Device class changes**: restart BLACS, check `logs/BLACS.log`
- **Analysis changes**: re-run lyse single-shot script on a recent h5
- **External GUI changes**: restart the GUI, verify ZMQ with `/check-guis`
- **After any BLACS change**: run a test shot, check h5 output in HDFView
- **Connection table property changes**: recompile → BLACS auto-loads new properties (no need to delete saved state)
- **BigSky Auto Re-Arm**: click Warmup/Arm Ext buttons → verify hardware responds; check "Auto Re-Arm Ext" → queue shots → verify auto-arm/restore in BLACS.log; queue 3+ → verify no re-arm between shots

## External GUI Registry

| Name | BLACS Device Class | GUI Codebase | BLACS Device Path | REQ-REP Port | PUB-SUB Port | Connection Table Name |
|------|-------------------|--------------|-------------------|-------------|-------------|----------------------|
| Laser Lock | `LaserLockDevice` | `GUIs\HF_Locking` | `userlib/user_devices/LaserLockDevice/` | 3796 | 3797 | `LaserLockGUI` |
| Rastering GUI | `RasteringDevice` | `GUIs\rastering` | `userlib/user_devices/RasteringDevice/` | 55535 | 55536 | `RasteringGUI` |
| BigSky YAG Hub | `BigSkyHub` | `GUIs\BigSkyControl` | `userlib/user_devices/BigSkyHub/` | 55540 | 55541 | `BigSkyLasers` |

Add new external GUIs to this table.

Each GUI codebase carries its own `.claude/agents/` domain agent: `HF_Locking`→`pid-persistence`, `rastering`→`ablation-tech`, `BigSkyControl`→`bigsky-yag-laser-controller`. Use the GUI-local agent for that GUI's internals; use `amo-expert`/`blacs-expert` for BLACS-side architecture. Never flag a GUI-local agent name as broken without checking `GUIs/*/.claude/agents/`.

## Do NOT Flag These

- **`__pycache__/` and `.ipynb_checkpoints/`** — auto-managed by Python and Jupyter
- **`GUIs/rastering*/calibration_data.json`** — operator live calibration data: **tracked but always dirty** (` M`). Never stage, commit, or `git restore` it; stage only your own files by name. Each rastering worktree has its own copy.
- **Single-occurrence log errors** without recurrence — yellow observation, not critical
- **`npx claude-mem status` saying "Worker is not running"** — known CLI bug (unwritten `.worker.pid`). Ground truth: `netstat -ano | grep 37777` LISTENING + `curl http://127.0.0.1:37777/api/health`
- Domain-specific suppressions (RunManager globals, NaN rows, deprecated kwargs) in `.claude/rules/`

## Available Tools

### Skills (auto-activate or invoke with /name)

- `/check-sequence` — validate sequence globals, devices, structure before compilation
- `/check-guis` — ping ZMQ ports to verify external GUIs are running
- `/debug-blacs` — standardized BLACS triage workflow (logs → routing → diagnosis)
- `/new-device` — scaffold a new external GUI BLACS integration (5-file pattern)

### Agents (launched automatically based on task type)

- `blacs-expert` — Qt threading, state machine, BLACS runtime internals, NI_DAQmx worker lifecycle, cross-device impact analysis
- `amo-expert` — sequences, connection tables, experiment design, RunManager
- `device-builder` — scaffolding new device classes (confers with blacs-expert + amo-expert)
- `lyse-analysis` — analysis scripts, Jupyter notebooks, utility API
- `labscript-diagnostics` — log parsing, error diagnosis, recurrence analysis
- `session-notes` — background note-taking during sessions (sonnet, lightweight)
- `wrap-up` — end-of-session deliverables (commits, lab notes, introspection, context updates)
- `context-auditor` — audits context health against best practices; researches new practices with multi-source corroboration
- Orchestration rules (routing table, workflow, deliverables checklist) auto-load via `agent-workflow` skill

## Reference Documentation

Docs load via path-scoped rules (`.claude/rules/ref-*.md`) when editing matching files:
- `docs/blacs-state-machine.md` — canonical BLACS state machine + per-shot lifecycle (fork-specific MODE_POST_EXP); loads for `user_devices/`, `blacs/`
- `docs/blacs-device-patterns.md` — RemoteControl + NI_DAQmx patterns incl. latched-lines mechanism (loads for `user_devices/`, `blacs/`)
- `docs/remotecontrol-zmq-protocol.md` — canonical ZMQ protocol for external-GUI devices: REQ-REP + PUB-SUB + monitor-snapshot pattern (loads for `user_devices/`, `GUIs/`)
- `docs/external-guis-architecture.md` — per-GUI architecture for HF_Locking / rastering / BigSkyControl (loads for `user_devices/`, `GUIs/`)
- `docs/main-experiment-overview.md` — this machine's CT topology, channels, sequences, globals model (loads for `labscriptlib/Main_Experiment/`)
- `docs/shot-h5-layout.md` — per-shot HDF5 file layout incl. `/images/` camera group + LaserLockGUI case study (loads for `user_devices/`, `blacs/`, `analysislib/`)
- `docs/labscript-api.md` — labscript DSL, device drivers, sequence functions (loads for `labscriptlib/`, `user_devices/`)
- `docs/analysis-api.md` + `docs/ni-scope-conventions.md` — analysis utilities (loads for `analysislib/`)
- `docs/hf-locking-rates.md` — HF_Locking refresh-rate inventory + lock thresholds (loads for `GUIs/HF_Locking/`, `user_devices/LaserLockDevice/`)
- `docs/yag-laser-physics.md` — Nd:YAG laser physics, trigger modes, serial commands (loads for `user_devices/BigSky*`, `GUIs/BigSkyControl/`)
- `docs/matisse-c-external-locking.md` — Matisse C-S external-lock candidate architectures: baseline WS7-direct PID, Counterdrift plug-in, DSP External Input bypass, GoTo overlay; ruled-out paths + comparison matrix; corrected failure mechanism (Slow Piezo search on ref-cell unlock) (loads for `user_devices/LaserLockDevice/`, `GUIs/HF_Locking/`, `labscriptlib/Main_Experiment/`, `analysislib/Main_Experiment/`)
- `docs/known-latent-issues.md` — catalog of latent bugs / conditional issues; no auto-load (reference-on-demand)
- `Labscript-Confluence-2026-02-11.pdf` — Lab-specific Confluence docs
- Official labscript docs: https://docs.labscriptsuite.org/ (reference only — our fork code takes precedence)
