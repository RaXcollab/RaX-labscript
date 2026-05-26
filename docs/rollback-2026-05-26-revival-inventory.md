# Rollback 2026-05-26 — Pre-ZMQ-v2 Restoration

## TL;DR

On Tuesday 2026-05-26 the parent repo (`labscript-suite`), `labscript-devices`,
`GUIs/HF_Locking`, and `GUIs/BigSkyControl` were reset to pre-Thursday-2026-05-21
states because the in-progress ZMQ v2 protocol cutover was incomplete and broke
runtime behavior (RemoteControl subclasses missing `_extra_topics` and related
data-driven-subscriber-registry attributes). `GUIs/rastering` was already at a
pre-cutover commit and was not touched. Backend repos (`blacs`,
`labscript-utils`) had no commits this week and were not touched.

All discarded work is preserved on archive refs. **No commits were lost.** This
doc is the index for picking that work back up later, one piece at a time, on
topic branches rather than in a stacked landing run.

## Symptoms that triggered the rollback

- `AttributeError` on subclasses of `RemoteControl` for `_extra_topics` (and
  other `_*` items) introduced by the new data-driven subscriber registry
  (`refactor(RemoteControl): data-driven subscriber registry`, commit
  `11db110` on the rolled-back master).
- PUB-SUB message routing silently dropping topics that no subclass had
  registered for in the new contract.
- Operator could not run shots reliably between Fri 2026-05-22 and Tue 2026-05-26.

Root cause: the subscriber-registry refactor changed the base-class contract
(subclasses must populate `_extra_topics`) and was followed by an even larger
ZMQ v2 cutover (parent + 3 GUIs over `refactor/zmq-v2-base` and
`refactor/zmq-v2-hardening`) before all `RemoteControl` subclasses had been
migrated to the new contract. The two refactors compounded — each was
individually plausible, together they left subclasses in a state where the
base class assumed attributes the subclasses had not been updated to define.

## Final per-repo state (post-rollback)

| Repo | Branch | HEAD | Date |
|------|--------|------|------|
| `labscript-suite` (parent) | `master` | `84c0c98` | 2026-05-22 17:32 (`f08647b` + cherry-picked `538dbd3`) |
| `labscript-devices` | `master` | `aed191f` | 2026-05-19 23:55 |
| `GUIs/HF_Locking` | `main` | `ba6524a` | 2026-05-19 23:41 |
| `GUIs/BigSkyControl` | `main` | `d5e64fc` | 2026-05-19 23:39 |
| `GUIs/rastering` | `main` | `bf9fee2` | 2026-05-21 23:58 (untouched) |
| `blacs` | `master` | unchanged | n/a |
| `labscript-utils` | `master` | unchanged | n/a |

The lone cherry-pick on the parent (`538dbd3`,
`refactor(RasteringTab): persist raster_check_box state`) was kept so the
parent's `RasteringTab` stays in sync with `GUIs/rastering`'s already-shipped
checkbox-persistence work.

## Archive refs (where the dropped work lives)

Every reset created a `archive/pre-rollback-2026-05-26` tag pinned at the pre-reset
HEAD in its repo. Two repos got additional named branches for ergonomic revival:

| Repo | Tag | Branch (extra) |
|------|-----|----------------|
| `labscript-suite` | `archive/pre-rollback-2026-05-26` (= `069c2ca`) | `archive/zmq-v2-attempt-1` (= `069c2ca`) |
| `labscript-devices` | `archive/pre-rollback-2026-05-26` (= `e975eeb`) | — |
| `GUIs/HF_Locking` | `archive/pre-rollback-2026-05-26` (= `3ac543b`) | — |
| `GUIs/BigSkyControl` | `archive/pre-rollback-2026-05-26` (= `24d174d`) | `archive/mixin-extraction-2026-05-22` (= `24d174d`) |

All four tags and both branches were pushed to `origin` (the `RaXcollab/*`
forks). To inspect what was dropped:

```
git -C <repo> log <current-HEAD>..archive/pre-rollback-2026-05-26 --oneline
git -C <repo> diff <current-HEAD>..archive/pre-rollback-2026-05-26 -- <path>
```

Pre-existing off-master topic branches in the parent
(`zmq-v2-cutover`, `chore/subagent-rule-inheritance`,
`docs/zmq-v2-spec-footnote`, `feat/spinnaker-gige`,
`tests/userlib-worker-tests`) were not touched and remain on origin.
GUI-repo `zmq-v2-port` branches (`HF_Locking`, `rastering`, `BigSkyControl`)
also remain on their forks.

## Revival inventory

Each item below is a distinct piece of work that was dropped or paused. Pick
them up individually on topic branches. Do not bundle.

### 1. RemoteControl data-driven subscriber registry

- **Commits:** `11db110` (`refactor(RemoteControl): data-driven subscriber registry`),
  `242dc99` (merge).
- **Lives on:** `archive/zmq-v2-attempt-1` (parent).
- **What it does:** Replaced `RasteringTab`'s wholesale override of the PUB-SUB
  subscriber loop with a base-class `_extra_topics` registry that subclasses
  populate.
- **Why it broke:** Other `RemoteControl` subclasses (LaserLockDevice,
  BigSkyHub) never had their `_extra_topics` populated, so any topic they
  expected to handle silently went unrouted. Base-class assumed the attribute
  always exists; it didn't on subclasses that hadn't been touched.
- **Revival approach:** Reland on a topic branch. Before merging, grep all
  `RemoteControl` subclasses and confirm each defines `_extra_topics` (even
  if empty). Add a base-class default `_extra_topics = {}` as a safety net so
  the refactor degrades gracefully on un-migrated subclasses.

### 2. ZMQ v2 protocol foundation

- **Commits:** `ef24a6d` (foundation), `a07bf03` (base merge),
  `0bb8722` (handler-contract hardening), `1b0693a` (hardening merge),
  `6795f4a` (spec merge).
- **Lives on:** `archive/zmq-v2-attempt-1` (parent), plus the
  `userlib/external_gui_lib/` directory contents at that tip.
- **Companion work on GUI repos:** `zmq-v2-port` branches in `HF_Locking`,
  `rastering`, `BigSkyControl` (all untouched by this rollback — still on
  their forks).
- **What it does:** Replaces the v1 ad-hoc JSON-over-ZMQ contract between
  BLACS RemoteControl devices and the external GUIs with a versioned v2
  protocol (typed handler signatures, structured rejection, dropped re-decode
  hot path on the worker side).
- **Why it failed:** Cutover was attempted as one big atomic landing
  (`reference_zmq-v2-cutover-pattern.md` in auto-memory). The protocol break
  shipped before all callsites in the parent had been ported — and item 1
  (subscriber registry) shipped as a prerequisite without per-subclass
  coverage, taking down the live operator workflow.
- **Revival approach:** Treat v2 as a sequenced multi-PR effort, not a
  cutover. First land item 1 (subscriber registry) with default safety net
  + per-subclass coverage. Then port one GUI at a time, with the parent
  speaking both protocols (`protocol_version` field) until the last GUI is
  cut over.

### 3. RemoteControl graveyard cleanup

- **Commits:** `e2b9f68` (merge), `4d46acb` (rename graveyard CTs).
- **Lives on:** `archive/zmq-v2-attempt-1` (parent).
- **Companion in `labscript-devices`:** `f5225ef` + `e975eeb` (removed the
  dead `labscript-devices/labscript_devices/RemoteControl/` tree). Both
  reverted; tree restored on disk and in HEAD.
- **What it does:** Deletes/renames-aside graveyard files that were
  superseded by the canonical `userlib/user_devices/RemoteControl/` tree.
- **Why it was dropped:** Bundled with the rollback for consistency, not
  because it caused harm. The deleted tree was already dead
  (`reference_two-remotecontrol-trees.md` in auto-memory:
  `labscript_devices/RemoteControl/` has its `register_classes.py`
  commented out and no live imports).
- **Revival approach:** Reland independently on a clean topic branch.
  Re-confirm zero imports of `labscript_devices.RemoteControl` before
  deleting.

### 4. jim_DIO sequence fix

- **Commits:** `3f3239a`
  (`fix(sequences): jim_DIO_acquire ENH_start/ENH_end -> ENH_START/ENH_DURATION`),
  `a30346d` (merge).
- **Lives on:** `archive/zmq-v2-attempt-1` (parent).
- **What it does:** Real sequence rename in `labscriptlib/Main_Experiment/`
  unrelated to the ZMQ refactor — a global rename from `ENH_start`/`ENH_end`
  to `ENH_START`/`ENH_DURATION`.
- **Why it was dropped:** Dropped with the rest per user direction; not part
  of the ZMQ mess. Safest to re-apply via cherry-pick.
- **Revival approach:** `git cherry-pick 3f3239a` onto current master. Verify
  globals + sequences compile in RunManager after.

### 5. BigSky mixin extraction refactor

- **Commits (on `GUIs/BigSkyControl`):** 12 commits Fri 2026-05-22 from
  `5a7c43b` parent up through `24d174d`. Splits `SingleLaserController` out
  of `BigSkyControllerAmbitious.py` into 4 mixin sibling files:
  `serial_io.py` / `remote_bridge.py` / `compound_sequences.py` /
  `laser_commands.py`.
- **Lives on:** `archive/mixin-extraction-2026-05-22` branch
  (`GUIs/BigSkyControl`).
- **What it does:** Pure structural refactor — `BigSkyControllerAmbitious.py`
  shrinks to 164 LOC and only holds the `SingleLaserController` shell that
  composes the four mixins. No behavior change, no protocol change.
- **Why it was dropped:** Bundled with the rollback for strict
  pre-Thursday consistency per user direction. Not implicated in the
  `_extra_topics` bug.
- **Revival approach:** Cherry-pick the 12 commits as a series (or merge
  the archive branch directly). The mixins are independent and could even
  be relanded in 4 PRs as originally structured (steps 1/4 → 4/4 of
  T0.6 item 2.6).
- **Memory note:** `reference_bigsky-controller-split.md` in auto-memory
  documents the post-mixin architecture as the canonical 2026-05-22 state.
  After this rollback that memory is **stale** until the refactor is
  relanded — see "Memory entries to revisit" below.

### 6. HF_Locking tests + cleanups

- **Commits (on `GUIs/HF_Locking`):** `7bd4d5c` (test pin for canonical
  lock-wait invariants H1-H6, 6 tests), `9d59d73` (delete stale `wlm_utils.py`
  TODO + CLAUDE.md drift), `57b783f` and `3ac543b` (merge commits).
- **Lives on:** archive tag `archive/pre-rollback-2026-05-26` (`HF_Locking`).
- **What they do:** Pin canonical invariants H1-H6 in a test file (lock-wait
  AND-gate contract) + remove dead TODO + minor CLAUDE.md drift fix. All
  clean, all reviewable in isolation.
- **Why dropped:** Bundled with the rollback per user direction (strict
  pre-Thursday).
- **Revival approach:** Cherry-pick the two code commits (`7bd4d5c` + `9d59d73`).
  The merge commits are auto-regenerated.

### 7. Matisse external-lock investigation docs

- **Commits:** `aca9b13` (initial), `93d2488` (rewrite + parallel-investigation
  runbook), `ae493e9` (rewrite with concrete remote-control protocol
  findings — LocalGoTo, Network DLL, no Counterdrift API).
- **Lives on:** `archive/zmq-v2-attempt-1` (parent), specifically the file
  `docs/matisse-c-external-locking.md` which was deleted by the rollback.
- **What it is:** Reference doc for Matisse C-S external-lock candidate
  architectures and ruled-out paths. Per auto-memory entry on this work,
  the third rewrite was the first one with real source-citation discipline
  (read all primary docs first, tag inferred-vs-asserted claims).
- **Why dropped:** Bundled in the rollback. Pure documentation, not part of
  the ZMQ bug.
- **Revival approach:** `git checkout archive/zmq-v2-attempt-1 --
  docs/matisse-c-external-locking.md` then commit. Also re-apply the
  CLAUDE.md reference-section line that pointed at it (was at parent
  `CLAUDE.md` line ~143 area before the rollback).

### 8. ZMQ v2 protocol spec (standalone doc)

- **Commits:** `65addcf` (spec), `ec03e3a` (§10 sign-off Q1-Q4).
- **Lives on:** `archive/zmq-v2-attempt-1` (parent).
- **What it is:** Standalone protocol specification doc for v2. Lives in
  `docs/` on that branch.
- **Revival approach:** Restore alongside or before item 2 (foundation).
  Useful as a contract reference even without immediate cutover.

### 9. Lab notes from this week

- **Files (untracked on disk now):**
  - `notes/2026-05-22_Matisse-External-Locking-Architecture-Investigation.html`
  - `notes/2026-05-23_ZMQ-v2-Cutover-Shipped.html`
  - `notes/2026-05-24_Phase-6-Hardening-Shipped.html`
  - `notes/2026-05-24_claude-mem-env-vars-reference.md`
- **Status:** Untracked, never committed (per the existing `notes/` convention).
  Survived the reset on disk — they were never in git. Operator-readable record
  of the work that was done.
- **Action:** Leave on disk. Useful narrative context for whoever picks up
  any of the revival items.

## Suggested revival order

1. **#4 jim_DIO sequence fix** — single cherry-pick, low risk, immediate
   operator value.
2. **#6 HF_Locking tests + cleanups** — two cherry-picks, low risk, locks in
   canonical lock-wait invariants.
3. **#7 Matisse docs** — pure documentation restore, zero runtime risk.
4. **#5 BigSky mixin refactor** — cherry-pick the 12-commit series. Pure
   structural; no protocol/behavior change. Restores the post-2026-05-22
   canonical architecture and clears a stale auto-memory entry.
5. **#3 RemoteControl graveyard cleanup** — re-verify no imports of dead tree,
   then re-apply.
6. **#1 RemoteControl subscriber registry** — reland with default
   `_extra_topics = {}` on the base class + per-subclass population audit.
   This is the load-bearing contract change for v2; must ship cleanly before v2.
7. **#8 ZMQ v2 protocol spec doc** — restore as a standalone reference.
8. **#2 ZMQ v2 protocol cutover** — sequenced rollout, **not atomic**: parent
   speaks both protocols, then port one GUI at a time, with a soft sunset
   window per GUI.

## Memory entries to revisit (potentially stale)

After this rollback, the following auto-memory entries describe state that no
longer matches the on-disk reality. Treat them as describing intent that the
revival items above are meant to restore, not current ground truth.

- **`reference_bigsky-controller-split.md`** — describes the 4-mixin split
  shipped 2026-05-22. After rollback, BigSky is back to the monolithic
  `SingleLaserController` in `BigSkyControllerAmbitious.py`. Stale until
  revival item #5 lands.
- **`reference_zmq-v2-cutover-pattern.md`** — describes the atomic
  cutover-style multi-repo protocol break. After rollback that cutover is
  undone; the *pattern itself* is still a valid technique to reference, but
  the implementation it described is gone until revival item #2 lands.
- **`reference_inmemorytransport-test-pattern.md`** — references v2 test
  infrastructure. Tests are gone with the v2 code. Stale until revival item #2
  lands.
- **`reference_composition-over-qobject-mixin.md`** — generic principle, but
  the BigSky example it draws on is rolled back. Principle holds; example is
  in the archive branch.

## Forensics — why the refactor was incomplete

Three failure modes compounded:

1. **Base-class contract change without subclass-coverage audit.** The
   subscriber-registry refactor added `_extra_topics` as a required-ish
   attribute on `RemoteControl` subclasses but only migrated `RasteringTab`.
   No grep-all-subclasses gate before merge.
2. **Atomic multi-repo cutover with no per-leg dual-protocol period.** The
   ZMQ v2 cutover was modeled as one-shot break (parent + 3 GUIs in lockstep)
   with no dual-protocol window. This pattern is well-documented in
   auto-memory as `reference_zmq-v2-cutover-pattern.md` — it works for tightly
   coupled mono-repos, but here the integration surface was wider than the
   pattern's assumptions accommodated.
3. **Destabilizing work landed on `master` rather than a topic branch.** The
   `master` branch is what the operator runs between shots. Per the
   auto-memory feedback `feedback_destabilizing-work-on-branch.md`, work that
   leaves the codebase un-runnable at intermediate states must live on a topic
   branch, not on master. Items 1+2 above shipped to master and broke shots
   for ~4 days.

The corresponding correctness gates for the next attempt:

- Per-subclass coverage grep + default value on the base before any
  contract-change refactor.
- Dual-protocol window for ZMQ v2 — parent speaks both, GUIs port one at a
  time, sunset on a known date with the v1 path explicitly tagged for
  removal.
- All multi-stage refactors stay on a topic branch until the full sequence is
  green; only the merge-to-master happens after the full chain is verified
  end-to-end.
