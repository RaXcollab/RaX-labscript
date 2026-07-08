# Open Items — cross-session ledger

Deferred work with an owner and a gate. A Claude session that flags something as "worth a follow-up" MUST add it here (or fix it) — prose footnotes don't survive compaction. Remove items when done.

## Gated on operator / hardware
- **Camera-fix hardware validation** (2026-07-08): after BLACS restart, confirm `Saving 1/1 images` incl. one slow-lock shot, no 214/101 in BLACS.log, manual snap returns an image. Gates: retroactive wrap-up (plan T7), P4 connection-table commit.
- **Hooks live-fire test** (plan T2 step 5): fresh session → session-start checklist appears; scratch edit under `userlib/user_devices/` → gate message fires once, no loop.

## Code follow-ups (NuvuCamera, pre-existing, audit-flagged 2026-07-08)
- `errorHandling` 107 dead `pass` — falls through and closes the camera; needs `return` if 107 is benign ([nc_camera.py:108](userlib/user_devices/NuvuCamera/Nuvu_sdk/nc_camera.py)).
- `get_bias` exposure leak on mid-call failure (no current callers).
- Abort-during-continuous double-resume (fork T2M × inherited `abort()` both resume continuous).

## Context follow-ups
- Refresh stale codebase digests (`.claude/agent-memory/codebase-digests/cameras-and-scope.md`, `backend-core.md`) — predate 2026-07-07 merges.

## Standing queues (see plans)
- Z1–Z4 ZMQ-v2 cutover set (runbook: `~\.claude\plans\2026-07-07-pr-queue.md`); P4/P6 gated; BigSky refactor branches post-cutover.
