# Open Items — cross-session ledger

Deferred work with an owner and a gate. A Claude session that flags something as "worth a follow-up" MUST add it here (or fix it) — prose footnotes don't survive compaction. Remove items when done.

## Gated on operator / hardware
- **Camera-fix hardware validation** (updated 2026-07-08): morning merges VERIFIED (19:46 15-shot queue clean). Remaining: BLACS restart to activate the overnight hardening (b75b98b + labscript-devices b32c97e) — checklist in `notes/2026-07-08_Nuvu-error27-hardening-and-teardown-fixes.html`; then one slow-lock shot + manual snap.
- **Hooks v2 settings-dispatch test** (plan T2 step 5, narrowed 2026-07-08): scripts smoke-tested 24/24 (both PS editions, byte-exact stdin) — remaining untested surface is Claude Code's settings-level dispatch only. Fresh session → checklist appears (also on `--resume`); scratch edit under `userlib/user_devices/` → audit gate fires once; chained `git add x && git commit` via Bash → blocked by git guard. Note: creating the audit-waiver marker will hit a permission prompt (allow-rule was classifier-denied; waiver now requires user click — keep it that way unless it annoys).

## Code follow-ups (NuvuCamera, pre-existing, audit-flagged 2026-07-08)
- ~~`errorHandling` 107 dead `pass`~~ FIXED in working tree by concurrent session (verified [nc_camera.py:109-116](userlib/user_devices/NuvuCamera/Nuvu_sdk/nc_camera.py#L109-L116) — 107 now returns without closing; 215/216 also reclassified no-close). Pending commit.
- ~~`get_bias` exposure leak~~ RESOLVED — get_bias/get_bias64 deleted 2026-07-08 (no callers; verified [Nuvu_cam_utils.py:217](userlib/user_devices/NuvuCamera/Nuvu_sdk/Nuvu_cam_utils.py#L217)). Pending commit.
- ~~Abort-during-continuous double-resume~~ FIXED in b75b98b (`should_resume_continuous` guard + idempotent `start_continuous`; cross-audited, 31/31 tests). All three audit-flagged NuvuCamera items now closed.

## Context follow-ups
- ~~Digest refresh~~ DONE 2026-07-08 (3 opus agents): `cameras-and-scope.md`, `backend-core.md`, `labscriptlib.md` all stamped "Refreshed 2026-07-08" and verified against post-merge code + working tree.
- Always-loaded budget: 11,713 → **7,996 tokens** after 2026-07-08 no-deferrals restructure (under 8k target; history in `.claude/agent-memory/context-auditor/audit-history.md`). Re-measure at next T8 run.
- `Open_cell2.py`: unused `latch_digital` import (post-rework leftover, flagged by digest refresh) — one-line cleanup at next sequence edit.
- **TiSa_1 channel-move merge gate** (added 2026-07-29): TiSa_1 is now WS7 **ch1** (was ch4; crosstalk). The `zmq-v2-cutover` branch still carries `connection=4` in `connection_table.py` (both TiSa_1 children) and double-stale HF docs; `HF_Locking-zmq-v2` has NO per-port tolerance mechanism yet claims one in its CLAUDE.md. Fix at rebase/merge or the move regresses. Full checklist: `docs/wavemeter-channel-move.md`. Physical steps (PID DAC cable output 4→1, WS7 per-channel PID migration) may still be pending — confirm with operator.
- **Graph rebuild gate** (added 2026-07-29): after the Z1–Z4 cutover merges, rebuild `graphify-out/graph.json` — `userlib/external_gui_lib/` gains real sources → first genuine GUI↔userlib structural bridge. Recipe + 13-check verify: `.claude/graphify/REFRESH.md`. Standing convention: after each rebuild, re-arm this item for the next large cross-root refactor rather than deleting it.

## Standing queues (see plans)
- Z1–Z4 ZMQ-v2 cutover set (runbook: `~\.claude\plans\2026-07-07-pr-queue.md`); P4/P6 gated; BigSky refactor branches post-cutover.
