# Session Handoff — RemoteControl PUB-SUB Monitor Snapshot Implementation

**Last active:** 2026-05-06, mid-implementation. VS Code restart pending.

## Resume instructions

1. Read this file fully.
2. Read [docs/superpowers/specs/2026-05-05-remotecontrol-pubsub-monitor-snapshot-design.md](../docs/superpowers/specs/2026-05-05-remotecontrol-pubsub-monitor-snapshot-design.md) — full empirically-validated design.
3. Read [docs/superpowers/plans/2026-05-05-remotecontrol-pubsub-monitor-snapshot.md](../docs/superpowers/plans/2026-05-05-remotecontrol-pubsub-monitor-snapshot.md) — 13-task TDD plan.
4. Resume execution at **Task 7 review + Task 8** (see "Where we are" below).
5. We are using the `superpowers:subagent-driven-development` skill — fresh subagent per task + spec review + code-quality review. The user said `/systematic-debugging` should be invoked if issues arise.

## Branch / commits

- Branch: `master` (user explicitly OK'd implementing on master).
- Working tree had many unrelated modifications already (analysis files, NI_SCOPE worker, etc.) — those are pre-existing, NOT this session's changes. Only touch the files in the plan.

## Commits made so far (latest at top)

```
ab65e01  RemoteControl: ensure EventBroker is up at tab-module import time   ← Task 7 implementer DONE, reviews pending
c72b762  RemoteControl: stop and join PUB-SUB drain thread in worker shutdown ← Task 6 ✅
1851f5c  RemoteControl: log final_monitor_values channel count in post_experiment ← Task 5 fix-up ✅
c3069f6  RemoteControl: snapshot initial_monitor_values from live drain cache  ← Task 4 (also bundled partial Task 5) ✅
925bc55  RemoteControl: add _pubsub_drain_loop with classified error handling  ← Task 3 ✅
f1298a3  RemoteControl: spawn PUB-SUB drain thread in worker init              ← Task 2 ✅
2cb9d9f  RemoteControl: add ls_zprocess + threading imports for PUB-SUB drain  ← Task 1 ✅
```

## Where we are

| Task | Status | Notes |
|---|---|---|
| 1. Worker imports + constants | ✅ DONE + reviewed | clean |
| 2. Worker init() drain spawn | ✅ DONE + reviewed | reviewer noted minor "comment overstates guarantee" — wording only, not a blocker |
| 3. Worker `_pubsub_drain_loop` | ✅ DONE + reviewed | reviewer noted minor `zmq.ZMQError` could be caught explicitly — non-blocking |
| 4. Worker `transition_to_buffered` swap | ✅ DONE + reviewed | implementer **overstepped** and bundled partial Task 5 |
| 5. Worker `post_experiment` swap | ✅ DONE (after fix-up commit `1851f5c`) | partial bundle in Task 4 omitted `logger.info`; fix-up added it |
| 6. Worker `shutdown()` extension | ✅ DONE + reviewed | clean |
| **7. Tab imports + check_broker()** | ⚠️ implementer DONE (`ab65e01`), spec/code reviews NOT YET RUN | Smoke test confirmed broker starts at port 57983 |
| 8. Tab `_post_to_internal_broker` method | ⏳ pending | next task |
| 9. Tab `connect_to_pubsub` extension | ⏳ pending | |
| 10. Tab `init_kwargs` cleanup (delete `pubsub_monitor_cache`) | ⏳ pending | |
| 11. Rastering tab `init_kwargs` cleanup | ⏳ pending | do back-to-back with Task 12 (no BLACS restart between) |
| 12. Rastering worker `pubsub_monitor_cache` swap | ⏳ pending | back-to-back with Task 11 |
| 13. Live BLACS shot acceptance | ⏳ pending | requires real BLACS instance + shot inspection |

## Anomaly history

**Bundling incident (Tasks 4 → 5):** the Task 4 implementer (haiku) silently extended scope into Task 5's `post_experiment` swap, but omitted the `logger.info` block. The first spec reviewer (haiku) hallucinated "no logger call here, matching expected behavior" — that was wrong. Resolution: ran systematic-debugging mentally, dispatched fix-up agent (commit `1851f5c`), then re-reviewed with sonnet. Lesson: **don't trust haiku for spec review on tasks where the implementer might have skipped optional-looking lines**. Use sonnet for re-verification when the diff is ambiguous.

## Resume — what to do next

1. **Spec-review Task 7** (commit `ab65e01`): verify [userlib/user_devices/RemoteControl/blacs_tabs.py](../userlib/user_devices/RemoteControl/blacs_tabs.py) lines 1-21 match the spec block in the plan's Task 7 step 1. The smoke test already confirmed broker comes up; the spec review is just confirming the file content. Use sonnet not haiku.
2. **Code-quality review Task 7** if spec passes. (Trivial — just imports + one method call. May skip if pressed for time, like Tasks 4-5 collapsed reviews.)
3. **Dispatch Task 8 implementer** — adds `_post_to_internal_broker` slot method to the base `RemoteControlTab`. Plan has the exact code block.
4. Continue through Task 13.

## Plan task references — exact code blocks

The plan at [docs/superpowers/plans/2026-05-05-remotecontrol-pubsub-monitor-snapshot.md](../docs/superpowers/plans/2026-05-05-remotecontrol-pubsub-monitor-snapshot.md) has the exact code blocks for each task — copy them verbatim into agent prompts.

## Skill / Agent dispatch pattern (template)

For each task:

```
1. TodoWrite: mark current task in_progress
2. Agent (general-purpose, model selection per complexity):
     prompt: full task block from plan + context paragraph + repo conventions + smoke test + commit instructions
3. Spec reviewer Agent (general-purpose, sonnet for non-trivial tasks):
     prompt: required end state + actual claim + verify-by-reading-file
4. Code quality reviewer Agent (superpowers:code-reviewer, sonnet for non-trivial):
     prompt: WHAT_WAS_IMPLEMENTED + PLAN_OR_REQUIREMENTS + BASE_SHA + HEAD_SHA + DESCRIPTION
5. TodoWrite: mark complete, advance next
```

Trivial mechanical tasks (e.g., Tasks 4, 5, 10, 11) can collapse spec+quality review into one or skip code quality. Non-trivial tasks (e.g., Tasks 2, 3, 8, 9, 13) get full two-stage review.

## Test files (already validated, don't re-run)

- [tests/zprocess_event_d_hybrid_test.py](../tests/zprocess_event_d_hybrid_test.py) — A1, A2, A3, A4, A5, A9 ✅
- [tests/zprocess_event_d_hybrid_test_2.py](../tests/zprocess_event_d_hybrid_test_2.py) — ls_zprocess wrapper, A10, A15, multi-worker ✅
- [tests/zprocess_event_d_hybrid_test_3.py](../tests/zprocess_event_d_hybrid_test_3.py) — empty-queue shutdown latency ✅
- [tests/zprocess_event_d_hybrid_test_4.py](../tests/zprocess_event_d_hybrid_test_4.py) — PUSH stress / backpressure ceiling ✅
- [tests/qt_multi_slot_test.py](../tests/qt_multi_slot_test.py) — A6 ✅

## Critical reminders

- **Conda activation required** for every Python command (CLAUDE.md):
  ```
  source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python ...
  ```
- **Master branch direct commits** (user-confirmed)
- **Do not push** to remote without explicit user confirmation (CLAUDE.md)
- **Tasks 11 and 12 must be back-to-back** — between them BLACS shouldn't be restarted (transient `AttributeError` window on `RasteringWorker.pubsub_monitor_cache`)
- **Task 13 is the live BLACS shot** — user must run BLACS and inspect shot h5 + logs against acceptance criteria in the plan and spec
