# zmq v2 cutover — four-repo architecture review (2026-07-30)

Four parallel read-only reviews: parent `zmq-v2-cutover` worktree, `GUIs/HF_Locking-zmq-v2`,
`GUIs/rastering-zmq-v2`, and `GUIs/BigSkyControl` ref `zmq-v2-port` (not checked out).
Graph blast radius: 309 nodes / 552 edges touching zmq/RemoteControl — see
`graphify-out/zmq-v2-focus.html`.

## Verdict

The v2 protocol itself is well designed. Every blocker is in the **rollout**, not the code:
branch hygiene (dropped commit, rolled-back base, stale forks) and the absence of an
enforced atomic-merge procedure for a protocol with no compatibility window.

## Blockers (fix before any merge)

1. **rastering — RESOLVED 2026-07-30.** The 2026-07-29 rebase had dropped origin-only commit
   `24b3ab4` (serve-failure circuit breaker, `error_signal` on dead transport, PUB-failure
   latch, 3 error-path tests). Deep audit (merge-tree simulated both directions) proved it
   was the ONLY loss — the headline ghost-attr fix was already local, folded in during rebase
   conflict resolution — and the sole cherry-pick conflict was one cosmetic comment line.
   Recovered as `0c16e7e` via `git cherry-pick -X ours 24b3ab4`; 18/18 protocol tests passed
   in the `rastering` env with the PYTHONPATH workaround (they `importorskip("zmq_v2")` and
   silently skip without it); pushed with explicit lease
   `--force-with-lease=zmq-v2-port:24b3ab4e...`. Residual: now-published commit `fa54aa9`
   points CLAUDE.md's canonical v2 spec at a machine-local worktree path (annotated
   temporary) — repoint to `docs/` after the parent cutover merges. Never
   `git rebase origin/zmq-v2-port` here: it regresses the base to old main and duplicates
   main's commits.

2. **BigSkyControl — RESOLVED 2026-07-30.** Rebuilt as `zmq-v2-port-rebuilt` (tip `c38e6ab`,
   8 commits on `main`@`896514f`): the 3 v2 commits cherry-picked clean (the rolled-back
   refactor never touched `HugeSkyController.pyw`, so no drift), plus tests-only `500746a`
   (conftest `hsc_module` fixture the B8 tests require — main never had it), plus both
   follow-on branches' payloads (`dd9da9f`+`e0652ad`+`1704f71`). Sole conflict was the
   expected modify/delete on the deleted mixin files; the 10 REJECTED-site changes were
   hand-applied to `BigSkyControllerAmbitious.py` with the emitted `error.code` set verified
   identical to upstream. Rolled-back tip `24d174d` is NOT an ancestor — zero resurrected
   commits. 38 passed / 0 skipped in `guis` env (all 21 B8 items genuinely ran; negative
   control confirmed). Old `zmq-v2-port` (`df8be86`) untouched — still never merge it.
   Not pushed. BigSky `main` is itself 1 ahead of origin (`896514f`, unpushed).

3. **The `zmq_v2` import mechanism — pre-merge slice DONE 2026-07-30; rest is by design
   post-merge.** The silent-skip trap is closed: `ZMQ_V2_REQUIRED=1` env gate landed in all
   three GUI conftest files (rastering `c670dfd`, HF `aa99a75`, BigSky `c38e6ab`) — with it
   set and `zmq_v2` absent, pytest dies at collection with a loud ImportError instead of
   "N skipped, exit 0". Proven both directions in all three repos. Still true until the
   parent merge lands `zmq_v2.py` on parent main: HF GUI and BigSky hub fail to launch at
   import time (BigSky loses even manual laser control — its `zmq` import is guarded, the
   `zmq_v2` one is not). Post-merge follow-up (in the runbook): make `external_gui_lib` a
   real package and delete the `sys.path` arithmetic from all three GUIs.

4. **Runbook + version assertion — RESOLVED 2026-07-30** (on the cutover branch, not
   pushed). The merge stays atomic-or-broken, but it now has teeth and a script:
   - Runbook written: `docs/zmq-v2-cutover-runbook.md` (worktree commit `699839f` +
     fixup `4b35340`) — four branches, push-all-before-merge-any, BLACS restarts last,
     `/check-guis` gate, one real armed raster in step mode, rollback path. All 5 dangling
     `zmq-v2-cutover-playbook` references repointed to it.
   - Client-side reply-version assertion in `_raw_request` (commit `9eba416`): non-v2 reply
     now raises `RemoteRequestError` code `protocol_version_mismatch` ("that GUI is still
     on v1") instead of a misleading 5 s timeout. Pinned by
     `test_reply_version_gate.py` (mutation-checked, InMemoryTransport, no sockets).
   - Master merged into the branch (commit `101cce2`, 54 commits): exactly the two
     predicted conflicts (CLAUDE.md → master's HF lock spec kept + v2 bullets kept;
     matisse doc → master's copy). `zmq_v2.py` still tracked; TiSa_1 on connection=1.

## Feared risks that are NOT merge hazards (verified, not reasoned)

- **HF per-channel lock tolerance:** the v2 branch predates the feature but never touched a
  tolerance line. `git merge-tree main zmq-v2-port` → zero conflicts; merged tree keeps
  `LOCK_TOLERANCE_BY_PORT`/`lock_tolerance()` AND the v2 port, and passes 20/20 incl.
  `test_H2b_tisa1_port1_locks_at_1mhz_not_5mhz`. Merge `zmq-v2-port` INTO `main`; never copy
  the branch's `workers.py`/`display.py` over main's, never squash with branch as tree source.
- **TiSa_1 `connection=4` in the cutover worktree:** the branch never modifies
  `connection_table.py` (three-dot diff empty), so a normal 3-way merge keeps master's
  `connection=1`. The real parent-merge conflict is **`CLAUDE.md`** (resolve the HF lock-spec
  bullet toward master — per-port tolerance + ch1 note) and `docs/matisse-c-external-locking.md`
  (add/add; take master's newer copy).
- Residual operational hazard: running either stale worktree on hardware today = TiSa_1 on
  the crosstalk channel and/or 5 MHz tolerance instead of 1 MHz. Rebase before any
  hardware-in-the-loop v2 commissioning.

## Design assessment (the architecture question)

Strengths worth keeping: `Transport` protocol seam (`zmq_v2.py:57-68`) — 31 protocol tests +
all GUI test suites run over `InMemoryTransport` with no sockets; composition over
inheritance in all three GUIs (nested `RemoteControlServerBase` subclass with `_outer`
backref, threading left to the host — QThread / daemon thread / Qt-signal routing all
preserved); typed statuses with structured `{code, message, retryable}`; capability
advertisement validated at import time; hard sunset = no dual-path code; the port fixed real
v1 bugs (unguarded `float()` killing the rastering zmq thread; HF `wait_for_lock`
absence-defaulting to True — the 2026-07-02 hang, now pinned by `test_H8`).

Weaknesses, ranked:
1. One-directional version check (client trusts; see Blocker 4).
2. Library distribution by relative path (Blocker 3).
3. Unthrottled error loops: rastering `_zmq_loop` catch-all with no delay (hot-spin that
   *republishes heartbeat* — dead command channel looks healthier than normal; fix restored
   by `24b3ab4`); same hole in HF `ZMQRepWorker.run()` — add `time.sleep(0.05)`.
4. BigSky server-side 10 s future timeout > client 5 s → typed TIMEOUT never delivered,
   retries cascade onto a still-blocked daemon thread (fix in
   `refactor/timeout-constant-disconnect-test`).
5. `response["value"]` indexed without presence check at `blacs_workers.py:547/:563/:577`
   (encode_reply omits `value` when None → KeyError in a periodic poll bricks the tab).
6. `check_status` still routes through raising `_check_response` (latent — sole caller is
   unregistered) — route through `_skip_non_success_read` + add test.
7. Dead code traps: HF write-only `wait_for_lock` ctor param (named after the flag that
   caused the 2026-07-02 hang); unused `PROTOCOL_VERSION` imports (HF + rastering);
   rastering test fixture still stubs ghost attr `_raster_iter` on a MagicMock, so the
   path-emptiness guard is never exercised (origin's `24b3ab4` fixes this too).
8. BigSky handlers accept `args` and silently discard it — log or reject unknown keys.

## Hygiene / follow-ups

- **HF `main` is 6 commits ahead of origin** — both safety-net commits (per-channel
  tolerance, ch4→ch1) exist only on this machine. Verified push-ready 2026-07-30: tree
  clean, suite green on main incl. `test_H2b`. Push `main` first.
- **HF `zmq-v2-port` has diverged from its origin (ahead 6 / behind 3) — benign.**
  Range-diff shows all three origin-only commits patch-identical to local ones (a clean
  rebase, unlike rastering's); local is a strict superset. Push with
  `--force-with-lease=zmq-v2-port:<origin SHA>`; nothing is lost.
- ~~Parent branch is 54 commits behind master~~ — DONE 2026-07-30, merge commit `101cce2`.
- `.githooks/pre-push` `TEST_PATHS` misses `RemoteControl/tests/` and `BigSkyHub/tests/`
  (10 of 41 new tests never run in the gate) — post-merge follow-up on master. Caveat
  found 2026-07-30: a whole-tree `pytest userlib/` hits 9 pre-existing collection errors
  (compile-on-import sequences + `double_import_denier` on dual import paths) — the hook
  must keep per-directory invocation; don't "fix" it by pointing at `userlib/`.
- Parent branch scope creep: ~1,285 lines of Matisse docs, `jim_DIO_acquire.py` fix,
  `.py.bak` renames — independently mergeable; one of them is the add/add conflict.
- ~~BigSky `zmq-v2-port` is 1 doc commit behind main (`896514f`)~~ — moot: the rebuilt
  branch starts from main's tip, which includes it.
- `main` is not currently an ancestor of ANY of the three GUI port branches — each needs
  its own `main` merged in during pre-flight (runbook Phase 0), then that GUI's tests re-run.
- numpy/BLAS native crash in the `guis` env (`blas_fpe_check`, `0xc06d007f`) aborts full HF
  suite runs on BOTH branches — environmental, fix separately
  (`conda install -n guis --force-reinstall numpy`).

## Test evidence

- rastering v2 (PYTHONPATH workaround): **66 passed** (15 protocol); origin has 18 protocol
  tests — 3 error-path tests missing locally.
- HF v2 (workaround, H6 deselected for the numpy crash): **19 passed**; merged-tree run:
  **20 passed** incl. H2b. Without workaround: **20 skipped, exit 0**.
- Parent: 31 protocol tests (V1–V11) + 10 device tests on the branch.
- BigSky: 10 B8 protocol tests reviewed statically (not run — working tree on `main`);
  all 15 GUI tests skip-not-fail when `zmq_v2` is absent.

## Suggested merge order

**The authoritative procedure is now the runbook** (`docs/zmq-v2-cutover-runbook.md` on the
cutover branch). Status of the original steps:

1. Pre-merge, per repo — **DONE 2026-07-30**: rastering `24b3ab4` recovered (pushed as
   `0c16e7e`, tip now `c670dfd` local); BigSky rebuilt (`zmq-v2-port-rebuilt` @ `c38e6ab`);
   client-side version assertion (`9eba416`) and runbook (`699839f`) on the parent branch;
   `ZMQ_V2_REQUIRED` gates in all three GUI repos. Remaining pre-flight (runbook Phase 0):
   merge each GUI's own `main` into its port branch + re-run tests.
2. Push round (runbook Phase 1, NOT started — needs authorization): HF `main` (6), rastering
   `main` (2), BigSky `main` (1, `896514f`), parent `master` (28 as of 2026-07-30); then the
   port branches — rastering plain push (1 ahead), HF force-with-lease (benign divergence),
   BigSky new branch; then parent `zmq-v2-cutover`.
3. Atomic merge round, restart order, verification, rollback: runbook Phases 2–3.
4. Post-merge: pre-push TEST_PATHS (per-directory only), package `external_gui_lib`, drop
   path injection, repoint rastering `fa54aa9`'s CLAUDE.md spec path, fix `guis`-env
   numpy/BLAS crash.
