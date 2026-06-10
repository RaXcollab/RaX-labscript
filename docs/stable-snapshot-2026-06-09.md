# Stable Snapshot — 2026-06-09 (pre-rastering re-session)

## Purpose

A known-good restore point captured **before** the 2026-06-09 rastering work
(Automatic Controls audit + "go-to-site" stepping feature). This is the safety
net the operator asked for so we never repeat the 2026-05-26 ZMQ-v2 rollback
that broke shots for ~4 days. Every repo's current runnable HEAD is pinned by an
annotated tag, pushed to origin. All new work happens on topic branches off
these HEADs — never on `master`/`main`.

## The restore anchor

Tag **`stable/2026-06-09-pre-rastering`** exists on every repo below, **pushed to
origin** (verified over the wire with `git ls-remote --tags origin`).

> **2026-06-10 restoration note:** the tag *refs* were found missing (locally AND
> on origin) in parent, blacs, labscript-devices, and labscript-utils — only the
> 3 GUI repos had them. The annotated tag objects listed below survived in each
> object database and were restored verbatim via `git update-ref` and pushed;
> re-verified over the wire 2026-06-10. If tags vanish again, suspect a pruning
> fetch or an incomplete original push ceremony.

| Repo | Branch | HEAD commit | Tag (annotated obj) | Remote | Auth |
|------|--------|-------------|---------------------|--------|------|
| `labscript-suite` (parent) | `master` | `d67b242` docs(rollback): document 2026-05-26 ZMQ-v2 rollback + revival inventory | `6fa3b5a` | `RaXcollab/RaX-labscript` | HTTPS |
| `blacs` | `master` | `e6784ee` Fix rgba() syntax in DO theme stylesheet for Qt CSS compliance | `5d1b1e1` | `RaXcollab/blacs` | SSH |
| `labscript-devices` | `master` | `aed191f` fix: replace Py3.8+ removed APIs in latent-unused drivers | `6ba2a95` | `RaXcollab/labscript-devices` | SSH |
| `labscript-utils` | `master` | `25cee8c` fix(device_registry): replace import imp with importlib.util | `0f176a1` | `RaXcollab/labscript-utils` | SSH |
| `GUIs/rastering` | `main` | `bf9fee2` data: recover live calibration_data.json (2026-05-20 auto-save) | `e57be7b` | `RaXcollab/rastering` | SSH |
| `GUIs/HF_Locking` | `main` | `ba6524a` docs: LOCK_CONSECUTIVE 2 -> 5 (Tier 1.1 follow-up) | `84334c6` | `RaXcollab/HF_Locking` | HTTPS |
| `GUIs/BigSkyControl` | `main` | `d5e64fc` fix(hub): populate LASER_SN_TO_CONNECTION; refresh agent + README + CLAUDE.md | `073a334` | `RaXcollab/BigSkyControl` | SSH |

### To restore a repo to this snapshot

```bash
git -C <repo> fetch origin
git -C <repo> checkout stable/2026-06-09-pre-rastering        # detached, inspect
# or hard-reset the branch (DESTRUCTIVE — operator confirmation required):
git -C <repo> checkout master   # or main
git -C <repo> reset --hard stable/2026-06-09-pre-rastering
```

> The tags pin **committed HEADs only**. The dirty operator files listed below
> are NOT in the tags — they are live operator data and were deliberately left
> untouched. A faithful restore must account for them separately.

## Dirty working-tree state at snapshot time (left untouched)

| Repo | Modified | Untracked (notable) |
|------|----------|---------------------|
| parent | `.claude/settings.local.json`, `userlib/labscriptlib/Main_Experiment/Globals/BaF_globals.h5`, `userlib/labscriptlib/Main_Experiment/sequences/Closed_cell.py` | `notes/*.html`+`.md`, `docs/CLAUDE.md`, `.claude/docs/`, `.claude/skills/check-guis/CLAUDE.md`, `.claude/skills/revert-to-main/`, `.claude/worktrees/`, `userlib/external_gui_lib/`, `userlib/user_devices/{RasteringDevice,RemoteControl}/CLAUDE.md`, `nul`, `1.20`, stray `C:...settings.json` |
| `GUIs/rastering` | `calibration_data.json` | `scripts/` |
| `GUIs/HF_Locking` | — | `Manual WS7 NeLAC (1).pdf`, `laser.ico`, `wlm_backups/` |
| others | — (clean) | — |

`BaF_globals.h5`, `Closed_cell.py`, `calibration_data.json` are operator live
state — do not commit them into the snapshot.

## Branch inventory (topic branches preserved across repos)

### parent `labscript-suite`
- `master` `d67b242` ← current, `= origin/master`
- `feat/spinnaker-gige` `645fa0d` — uEye→Spinnaker doc-sync (1 ahead; pairs with rastering branch)
- `zmq-v2-cutover` `1cbbbcf` (local) / `origin` `5863d35` — diverged; parked ZMQ-v2 cutover
- `archive/zmq-v2-attempt-1` `069c2ca` — archived ZMQ-v2 attempt (= `archive/pre-rollback-2026-05-26` tag)
- `docs/zmq-v2-spec-footnote` `40d9a27`, `chore/subagent-rule-inheritance` `10c5eca`, `tests/userlib-worker-tests` `e2147ab`
- Tag `archive/pre-rollback-2026-05-26` = `069c2ca`

### `GUIs/rastering`
- `main` `bf9fee2` ← current
- `feat/spinnaker-gige` `55cae38` — camera migration, **17 ahead of origin**, code-complete (see branch `HANDOFF.md`)
- `zmq-v2-port` `1cc4c12` — parked ZMQ-v2 transport rewrite (checked out in worktree, see below)

### backend repos
- `blacs`, `labscript-devices`, `labscript-utils`: local `master` only; numerous upstream-style `origin/*` branches preserved on the forks (maintenance/*, hacky_optimizations, performance_hacks, etc.).

### `GUIs/HF_Locking`, `GUIs/BigSkyControl`
- Both on `main` (HEADs above). Parked branches on origin per
  `docs/rollback-2026-05-26-revival-inventory.md`: `zmq-v2-port` (both),
  `archive/mixin-extraction-2026-05-22` (BigSky), plus
  `archive/pre-rollback-2026-05-26` tags on each.

## Worktrees (left untouched)

- Parent: main checkout `d67b242` + **locked** stale agent worktree
  `.claude/worktrees/agent-a6644a1302970fb10` @ `b9453f2`.
- `GUIs/rastering`: main checkout `bf9fee2` + **`GUIs/rastering-zmq-v2`** worktree
  holding the parked `zmq-v2-port` branch @ `1cc4c12`.

## Parked work (do not bundle — pick up individually)

- **`feat/spinnaker-gige`** (rastering + parent) — camera migration, awaiting operator validation. Candidate to land first; doesn't touch the controller.
- **`zmq-v2-port`** (rastering) + ZMQ-v2 cutover (parent `archive/zmq-v2-attempt-1`) — blocked by the rolled-back BLACS-side v2 dependency. See `docs/rollback-2026-05-26-revival-inventory.md`.
