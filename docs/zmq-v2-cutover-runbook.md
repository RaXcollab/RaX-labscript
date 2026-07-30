# ZMQ v2 cutover runbook

Operational checklist for landing the RemoteControl v2 protocol across all four
repos. Protocol reference is `docs/remotecontrol-zmq-protocol-v2.md`; this file is
only *how to land it without breaking the lab*.

**Branch tips below are as of 2026-07-30. Re-verify with `git log --oneline -1`
before starting — do not trust these SHAs blindly.**

## The one rule

**All four repos land in the same window, and BLACS restarts only after all four
have landed.** There is no partial-cutover mode.

Why: version enforcement is one-directional at the wire level. A v2 GUI server
hard-refuses a v1 envelope (`v1_protocol_refused`), and a v1 GUI server *accepts*
a v2 envelope but misreads it — it looks for `wait_for_lock` at the top level
where v2 now puts it inside `args`, so it falls back to the connection-table
default (True) and blocks. Parent-only merge therefore means **every manual
setpoint dies**. Since 2026-07-30 the client asserts the reply version
(`RemoteControl/blacs_workers.py::_raw_request`), so this now fails as
`protocol_version_mismatch` — "that GUI is still on v1" — instead of a
misleading 5 s ZMQ timeout. That is a better error message, not a working mode.

## What must land

| Repo | Branch | Tip | Target | Method |
|---|---|---|---|---|
| `RaXcollab/RaX-labscript` (parent) | `zmq-v2-cutover` | see `git log` | `master` | **merge** |
| `RaXcollab/HF_Locking` | `zmq-v2-port` | `aa99a75` | `main` | **merge** (port → main) |
| `RaXcollab/rastering` | `zmq-v2-port` | `c670dfd` | `main` | **merge** (port → main) |
| `RaXcollab/BigSkyControl` | `zmq-v2-port-rebuilt` | `d3c7676` | `main` | **merge** (rebuilt only) |

Parent worktree: `.claude/worktrees/zmq-v2-cutover`. GUI worktrees:
`GUIs/HF_Locking-zmq-v2`, `GUIs/rastering-zmq-v2`, `GUIs/BigSkyControl`.

### Traps — read before touching any branch

- **BigSkyControl: never merge `zmq-v2-port` (`df8be86`).** It is based on the
  mixin-extraction refactor that `main` hard-reset away on 2026-05-26 (archived as
  tag `archive/pre-rollback-2026-05-26`); merging resurrects 13 rolled-back
  commits. `zmq-v2-port-rebuilt` is the cherry-picked replacement and has `main`
  as a genuine ancestor — verify with
  `git merge-base --is-ancestor main zmq-v2-port-rebuilt`.
- **BigSky follow-ons are on the same poisoned base.** `refactor/structured-rejected`
  and `refactor/timeout-constant-disconnect-test` each carry 17–18 commits off
  `main`. Cherry-pick their own commits only — `dd9da9f` + `e0652ad` (structured
  REJECTED classification) and `1704f71` (`_REMOTE_CMD_TIMEOUT_S`; fixes the 10 s
  server vs 5 s client inversion that makes the server's typed TIMEOUT
  unreachable). Ship them in this round; they close this branch's own findings.
- **rastering: never `git rebase origin/zmq-v2-port`.** It regresses the base to
  old `main` and duplicates main's commits. The 2026-07-29 rebase already dropped
  `24b3ab4` once (serve-failure circuit breaker); it is back in as `0c16e7e`,
  an ancestor of the current tip. Confirm:
  `git merge-base --is-ancestor 0c16e7e zmq-v2-port`.
- **HF_Locking: push `main` first.** It carries 6 unpushed local commits including
  both safety nets (per-channel `lock_tolerance`, TiSa_1 ch4 → ch1). Merge
  `zmq-v2-port` **into** `main` — never copy the branch's `workers.py`/`display.py`
  over main's, never squash with the branch as tree source, or you silently revert
  the tolerance work.
- **`GUIs/rastering*/calibration_data.json` is always dirty.** Never stage,
  commit, or restore it. Stage your own files by name.

## Order of operations

### Phase 0 — pre-flight (can be done any time before the window)

- [ ] Parent branch has `master` merged in (done 2026-07-30) and the client-side
      version assertion (done 2026-07-30).
- [ ] BigSky rebuild committed, working tree clean, its protocol tests pass.
- [ ] Each GUI branch: merge its own `main` in and re-run that GUI's tests.
      `main` is not currently an ancestor of any of the three port branches.
- [ ] Run each suite with `ZMQ_V2_REQUIRED=1` so a missing `zmq_v2.py` is a hard
      error, not a silent skip. Without it HF reports "20 skipped, exit 0" —
      green while testing nothing.

### Phase 1 — push everything, merge nothing

- [ ] `git push` HF `main` (6 commits), rastering `main` (2), BigSky `main` (1).
- [ ] Push the three GUI port branches. HF `zmq-v2-port` has diverged from its
      remote (ahead 6 / behind 3) — needs `--force-with-lease=zmq-v2-port:<the
      SHA you just read from origin>`, never a bare `--force`.
- [ ] Push parent `zmq-v2-cutover`.

**Stop here and confirm all pushes succeeded before merging anything.**

### Phase 2 — merge all four

- [ ] Merge the three GUI port branches into their `main`s.
- [ ] Merge parent `zmq-v2-cutover` into `master`. Expect a `CLAUDE.md` conflict
      if master moved again: resolve the HF lock-spec bullet toward **master**
      (per-port tolerance, TiSa_1 on ch1) and keep the v2 protocol bullets.
- [ ] Confirm `userlib/external_gui_lib/zmq_v2.py` is on `master` — every GUI
      `sys.path`-injects `userlib/external_gui_lib`, and until this file is there
      the HF GUI and BigSky hub fail at import (BigSky loses manual laser control
      too: its `zmq` import is guarded, its `zmq_v2` import is not).

### Phase 3 — restart and verify, in this order

- [ ] Restart the three GUIs, then BLACS. Any order reaches the same end state
      once all four have landed; this order just keeps mismatch noise out of the log.
- [ ] Check `logs/BLACS.log` for
      `protocol_version_mismatch` or `v1_protocol_refused` — either means one side
      did not land; go to rollback, do not debug live.
- [ ] `/check-guis` — the gate. It sends a v2 HELLO and reports
      `v1_protocol_refused` explicitly (since `abf5bad`). All three must answer v2.
- [ ] One **real armed raster in step mode**. The `finished` handshake has zero
      integration coverage; this is the only thing that exercises it.
- [ ] `test_H2b` on HF (`test_H2b_tisa1_port1_locks_at_1mhz_not_5mhz`) — proves the
      merge kept the 1 MHz TiSa_1 tolerance on ch1.
- [ ] One manual setpoint per GUI from the BLACS front panel.

## Rollback

The GUI merges are **inert while the GUI processes keep running old code** — only
a restart loads v2. So:

1. `git revert -m 1 <parent merge commit>` on `master`, push.
2. Restart BLACS. It is back on v1.
3. **Any GUI you already restarted onto v2 must go back too** — a v2 server
   hard-refuses v1 BLACS. Check out that GUI's pre-merge tip (`git log --oneline
   -1 <main>@{1}` finds it) and restart the GUI process.
4. If you have not restarted the GUIs yet, steps 1–2 are the whole rollback.

Do not try to roll back one GUI and leave the others on v2 — same atomicity rule
in reverse.

## Post-merge follow-ups (not part of the window)

- `.githooks/pre-push` `TEST_PATHS` misses `RemoteControl/tests/` and
  `BigSkyHub/tests/` — 10+ tests never run in the gate.
- Make `external_gui_lib` a real package (`from external_gui_lib.zmq_v2 import
  ...`, the form the BLACS side already uses) and delete the `sys.path`
  arithmetic from all three GUIs.
- rastering `fa54aa9` points CLAUDE.md's canonical v2 spec at a machine-local
  worktree path — repoint it at `docs/remotecontrol-zmq-protocol-v2.md`.
- numpy/BLAS native crash in the `guis` env (`blas_fpe_check`, `0xc06d007f`)
  aborts full HF suite runs: `conda install -n guis --force-reinstall numpy`.
