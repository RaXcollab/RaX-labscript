# RaX Lab — Labscript Suite

> Load-bearing invariants: **Critical Conventions** below — read before mutating git, devices, or sequences.

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
- Organized by `<Experiment>\YYYY\MM\DD\<seq#>\` (experiment folder first, then date, then shot sequence number)

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

### Lab-Wide Invariants (load-bearing)

- **NEVER** `rm -rf`, `rm -r`, `mv` on directories without explicit user confirmation; use read-only commands (`ls`, `stat`, `test -d`) for diagnostics
- **Never tag backend repos (`blacs`, `labscript-devices`, `labscript-utils`) with non-`v*` tags** — setuptools_scm parses `git describe` at import time; a non-version tag reachable from HEAD crashes `import labscript_utils` → BLACS/RunManager cannot start. Pin backend baselines by commit hash (`docs/stable-snapshot-2026-06-09.md`).
- **Per-shot teardown** belongs in `post_experiment`, NOT `transition_to_manual` (T2M runs only at queue-end/abort/pause). MODE flags + probe details: `.claude/rules/device-lifecycle.md`.
- **HF lock spec (canonical):** lock acquires when **5** consecutive in-tolerance samples land within `lock_tolerance(port)` — default `5e-6 THz = 5 MHz`, TiSa_1 (ch1; moved from ch4 2026-07-29) override `1e-6 THz = 1 MHz` (since 2026-07-10) — with `LOCK_TIMEOUT_S = 60`. Code is authoritative — `GUIs/HF_Locking/workers.py:20-32`. Older "2 consecutive", flat-5-MHz, or TiSa_1-on-ch4 notes are stale; correct everywhere on contact. Channel moves: `docs/wavemeter-channel-move.md`.
- **Authoritative scan x-axis** for RemoteControl-programmed scans is `/devices/{dev}/remote_device_operation['{ch}'][0]` (the actual labscript intent, full float64). `front_panel`, `_AO/value`, and `monitor_values` lag, quantize, or were `float32` pre-2026-04-29.

### Verification

- **No "verified" / "not a bug" / "no record of X" without the artifact in this turn** — a command's output, a file:line just read, or a zero-hit search after ≥2 query variants. One failed/hung query ≠ absence: say "not confirmed yet" and keep looking, or hand the check to the user.
- **Sequence changes**: compile in RunManager → check for errors
- **Connection table changes**: compile + restart BLACS
- **Device class changes**: restart BLACS, check `logs/BLACS.log`
- **Analysis changes**: re-run lyse single-shot script on a recent h5
- **External GUI changes**: restart the GUI, verify ZMQ with `/check-guis`
- **After any BLACS change**: run a test shot, check h5 output in HDFView
- **Connection table property changes**: recompile → BLACS auto-loads new properties (no need to delete saved state)
- **BigSky Auto Re-Arm**: click Warmup/Arm Ext buttons → verify hardware responds; check "Auto Arm Ext" → queue shots → verify auto-arm/restore in BLACS.log; queue 3+ → verify no re-arm between shots
- **Userlib worker tests + pre-push hook (2.8c)**: SDK-free helpers in `userlib/user_devices/*/` carry unit tests at `<device>/tests/test_helpers.py`; the `.githooks/pre-push` hook runs them in the `labscript` conda env. Install once per checkout (contract + log path in the hook's header): `cp .githooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push`.

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
- `/repo-status` — branch, ahead/behind, dirty count, worktree-of for all 15 workspace repos (read-only, no fetch)
- `/h5-inspect [path]` — read-only shot h5 dump: tree, root attrs, `remote_device_operation` scan values (blank = latest shot)
- `/new-device` — scaffold a new external GUI BLACS integration (5-file pattern)
- `/github-auth-triage` — deterministic GitHub auth/MCP failure triage (never credential surgery first)
- `/graphify query "<q>"` — code navigation + intra-repo blast radius via `graphify-out/graph.json` (userlib, 3 backend repos, GUIs). AST-only: ZMQ + string-path worker wiring invisible — External GUI Registry stays authoritative. Caveats/rebuild: `.claude/graphify/REFRESH.md`

### Agents (launched automatically based on task type)

- `blacs-expert` — Qt threading, state machine, BLACS runtime internals, NI_DAQmx worker lifecycle, cross-device impact analysis
- `amo-expert` — sequences, connection tables, experiment design, RunManager
- `device-builder` — scaffolding new device classes (confers with blacs-expert + amo-expert)
- `lyse-analysis` — analysis scripts, Jupyter notebooks, utility API
- `labscript-diagnostics` — log parsing, error diagnosis, recurrence analysis
- `wrap-up` — end-of-session deliverables (commits, lab notes, introspection, context updates); expands the terse milestone log in `.claude/session-scratch.md`
- `context-auditor` — audits context health against best practices; researches new practices with multi-source corroboration
- Orchestration rules (routing table, workflow, deliverables checklist) auto-load via `agent-workflow` skill

## Reference Documentation

- `docs/*.md` auto-load via path-scoped rules — the doc↔path map is `.claude/rules/ref-*.md`
- `docs/remotecontrol-zmq-protocol-v2.md` — **canonical** v2 protocol for external-GUI devices: JSON envelope with `id`/`status` enum/`error.{code,message,retryable}`, `@handler` dispatch via `RemoteControlServerBase`, `InMemoryTransport` mock for tests. Shipped on topic branches awaiting coordinated cutover (`docs/zmq-v2-cutover-runbook.md`).
- `docs/remotecontrol-zmq-protocol.md` — **DEPRECATED** v1 reference (archaeological only; v2 servers refuse v1 envelopes per Q4 hard sunset)
- `docs/known-latent-issues.md` — latent-bug catalog, reference-on-demand (no auto-load)
- `Labscript-Confluence-2026-02-11.pdf` — lab Confluence export
- Official labscript docs: https://docs.labscriptsuite.org/ (reference only — our fork code takes precedence)
