# Session Handoff — Post-ZMQ-v2 Cleanup Plan

Written 2026-07-30 evening, after the v2 cutover landed on all four mains and the two
pre-restart fixes were committed. This is the work plan for everything the adversarial
review surfaced that was deliberately NOT fixed in the restart window, plus the runbook's
post-merge follow-ups.

**Read first:** auto-memory `zmq-v2-cutover-dependency.md` (cutover state, rollback recipe,
condensed review findings) and `docs/zmq-v2-cutover-runbook.md` (procedure/history).

## State at handoff

- v2 landed on all 4 mains 2026-07-30 (~12:15 EDT). Merge commits: parent `cc7e19a`,
  HF `4fafdcd`, rastering `020d590`, BigSky `98ff562`.
- **Pre-restart fixes committed but NOT PUSHED:** parent master `ee0eff1`
  (wait_for_lock forwarded through 3 tabs; missing-`value` read guards in
  `_skip_non_success_read`, `check_status`, BigSky `_verify_armed_state`) and
  rastering main `cd40a2c` (`_handle_check` returns typed
  `UNKNOWN_CONNECTION`/`position_not_initialized` instead of SUCCESS-with-None).
  **Do not re-fix these. Ask the user before pushing** (parent pre-push hook runs tests).
- Phase 3 (GUI/BLACS restarts, `/check-guis`, armed raster in step mode, manual setpoint
  per GUI, `test_H2b`) — **confirm with the user whether it has been run** before touching
  anything below. Post-restart: first HF buffered shot may pause up to ~60 s waiting for
  lock (new, correct behavior); fresh rastering start logs benign
  `position_not_initialized` skips.

## Priority 1 — BigSky setters: typed errors instead of None→SUCCESS (review finding 3)

**Verified defect.** `_handleRemoteCommand` (`GUIs/BigSkyControl/BigSkyControllerAmbitious.py:950-952`)
maps a `None` handler return to SUCCESS. The setters return `None` on failure paths:
`_remoteSetVoltage` bare-returns on serial parse error (`:973`) and falls through on serial
timeout; same class of hole in shutter, lamps, qswitch, qswitch_mode setters. The qswitch
arm is additionally a silent no-op-SUCCESS when `dangerMode` is off.

**Consequence:** BLACS `_last_sent_values` dedup caches the "sent" value and never re-sends
→ stale flashlamp voltage across shots with green statuses.

**Fix:** mirror `_setLampMode` (same file — the one setter done correctly): on serial
timeout/parse failure return a typed `REJECTED` reply with `error.{code,message,retryable}`.
For qswitch-arm with `dangerMode` off, return `REJECTED`/`danger_mode_off` (confirm wording
with operator) rather than silent SUCCESS. ~30 lines, 5 setters.

**COUPLING TRAP (do in the same pass):** BLACS-side `BigSkyWorker` string-sniffs reply
*message text* — `_verify_armed_state` matches `"unknown connection"`, `"laser disconnected"`,
`"rejected:"` (`userlib/user_devices/BigSkyHub/blacs_workers.py:523`), and `program_manual`
has similar sniffing. Either keep the exact wording in new error messages, or (better)
migrate the sniffers to `status` + `error.code`. Changing server wording without touching
the sniffers breaks the skip logic silently.

**After landing:** previously-masked failures will surface as REJECTED banners in BLACS —
expected and desired; do not read them as a regression. Needs BigSky GUI restart + one
manual setpoint + one queued shot to verify. Tests: extend `GUIs/BigSkyControl` v2 protocol
tests (38 passing baseline, `guis` env) with one failure-injection test per setter.

## Priority 2 — timeout inversion: measure, then fix (review finding 4)

Client sends all non-lock requests with `DEFAULT_TIMEOUT_MS = 5000`
(`userlib/user_devices/RemoteControl/blacs_workers.py:34`, chosen at `:356` solely by
`wait_for_lock`). Server work can plausibly exceed it: BigSky compound commands
(`start_lasing` ≈ 5 serial round-trips) and rastering synchronous manual moves (up to 10 s
motor travel). Client reports TIMEOUT while the server completes anyway.

- **Serial wall-times are UNVERIFIED — measure before coding.** Add/read timing logs on the
  BigSky and rastering servers during real operations; only then pick fix: per-action
  timeout table client-side (small) vs async-ack on the server (big — avoid unless needed).
- Related, same pass: BigSky replies `TIMEOUT` with `retryable: true` while the queued
  command may still execute → retry = double-execution (matters for `start_lasing`).
  Likely fix: `retryable: false` on command channels.
- Related, note only: REP+PUB share one thread in both GUI servers → heartbeat flap during
  long ops. Fixing this is a threading refactor; do NOT bundle it in — file it separately
  if the flap actually bothers operators.

## Priority 3 — robustness batch (small; verify each claim in-code first — these are
reviewer findings I did not independently re-verify)

- **Rastering finished-vs-cancel race:** operator Stop racing `move_to_next` can report a
  cancelled raster as cleanly `finished` (`raster_controller.py` `move_to_next` handler,
  ~`:419-446`). Re-check active/cancelled state under `_state_lock` before returning
  `extra={"finished": True}`.
- **HF serve loop has no failure backoff** (`GUIs/HF_Locking/workers.py` serve loop) —
  rastering and BigSky both got one; mirror it.
- **BigSky heartbeat publish unguarded** — the one PUB call not wrapped; an exception kills
  the whole ZMQ thread. Wrap like the other publishes.
- **`check_status` raise-on-read** (`userlib/user_devices/RemoteControl/blacs_workers.py:586`)
  contradicts the never-raise-on-read policy. It appears legacy (tab only registers
  `check_remote_values` polling; `status_monitor` is unused). Verify nothing calls it, then
  either delete method + tab's `status_monitor`, or align it to `_skip_non_success_read`.

## Priority 4 — docs / infra hygiene (from review + runbook follow-ups)

- `userlib/user_devices/RemoteControl/README.md:98-175` still teaches the v1 wire format
  with no deprecation banner → banner + pointer to `docs/remotecontrol-zmq-protocol-v2.md`.
- Spec doc drift in `docs/remotecontrol-zmq-protocol-v2.md`: HF's PUB topic exception
  missing from §4.1; PING optional fields documented but unimplemented; §1.1 v1-fallback
  sentence contradicts the Q4 hard sunset. Fix the doc to match code.
- `GUIs/rastering/CLAUDE.md` "Canonical v2 protocol spec" still points at the retired
  `.claude/worktrees/zmq-v2-cutover/docs/...` path → repoint to parent `docs/` on master.
- Pre-push hook runs 80/100 userlib tests — misses exactly `RemoteControl/tests` (15) and
  `BigSkyHub/tests` (5). Add both dirs to `.githooks/pre-push`, reinstall per parent
  CLAUDE.md §Verification (2.8c).
- Make `userlib/external_gui_lib` a real installed package and drop the three GUIs'
  `sys.path` arithmetic. Medium task: touches all three GUI repos + `rastering`/`guis`
  conda envs. Do as its own session.
- `conda install -n guis --force-reinstall numpy` (H6 BLAS crash), then drop the
  `--deselect ...test_H6...` from HF test invocations.
- Retire worktrees `.claude/worktrees/zmq-v2-cutover`, `GUIs/HF_Locking-zmq-v2`,
  `GUIs/rastering-zmq-v2` via `git worktree remove` — **never `rm -rf`**, requires explicit
  user confirmation. Note the rastering worktree has its own always-dirty
  `calibration_data.json`; `worktree remove` will refuse — resolve with the user, do not
  force.

## Standing traps (unchanged)

- Every python: `source ~/miniconda/etc/profile.d/conda.sh && conda activate <env>` —
  `labscript` (parent/userlib), `rastering` (rastering GUI), `guis` (HF + BigSky).
- Rastering tests: only run `tests/test_zmq_v2_protocol.py` + `tests/test_raster_pathmodel.py`
  while the GUI may be running — `test_command_queue.py`/`test_raster_goto_handlers.py`
  open the uEye camera and HANG.
- Never stage/commit/restore any `calibration_data.json`. Never merge BigSky old
  `zmq-v2-port` (`df8be86`) or `refactor/*`. Never rebase rastering onto
  `origin/zmq-v2-port`. Commit per-repo; never push without asking.
- Reviewer/auditor subagents: inject `docs/remotecontrol-zmq-protocol-v2.md` §1.3 by path
  and instruct them to Read it, or they flag canonical idioms (`extra={"finished":True}`,
  server-defined `error.code`) as fabricated.
- Rollback triggers for the cutover itself remain only `protocol_version_mismatch` /
  `v1_protocol_refused` in BLACS.log (recipe in memory). Everything in this handoff is
  normal bug work, not rollback material.

## Suggested order

1. Push `ee0eff1` + `cd40a2c` (with user OK) so all machines see the pre-restart fixes.
2. Priority 1 (BigSky setters + sniffing migration) — one session, one BigSky restart.
3. Priority 3 batch — small diffs, one restart per affected process.
4. Priority 2 — measurement first, separate session.
5. Priority 4 hygiene — fill-in work, any time.
