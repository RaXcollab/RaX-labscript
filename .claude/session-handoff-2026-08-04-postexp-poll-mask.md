# Handoff: MODE_POST_EXP missing from RemoteControl poll mask

**Status: analyzed and verified 2026-08-04 (blacs-expert). NOT implemented — user deemed low priority ("post experiment is quick in practice"); analysis confirms that instinct. This doc is the spec if/when it's picked up.**

## The fix (one line)

Add `|MODE_POST_EXP` (fork flag, =32, `blacs/blacs/tab_base_classes.py:63-64`) to the `@define_state` allowed-modes mask on `RemoteControlTab.check_remote_values` (`userlib/user_devices/RemoteControl/blacs_tabs.py:363-366`). Shared base → fixes LaserLock, BigSky, and Rastering tabs at once. Precedent: the fork's own base-class `check_remote_values` already includes it (`blacs/blacs/device_base_class.py:456`) — the omission in the RemoteControl override reads as an oversight, not a decision.

## Verified semantics (why impact is small)

- The 5 s poll IS allowed in `MODE_BUFFERED` and both transition modes → it runs throughout every shot. The blind window is only `MODE_TRANSITION_TO_POST_EXP + MODE_POST_EXP` = inter-shot bookkeeping (worker post_experiment is tens of ms; queue bookkeeping sub-second to low seconds).
- An out-of-mode tick is **DROPPED, not deferred** (`tab_base_classes.py:560-570`: the mode test gates enqueueing; the timer re-arms unconditionally). No backlog, no catch-up burst. Worst case = one missed 5 s update.

## The one unbounded exception (latent)

A device present in shot N but **absent from every later queued shot** gets stranded in `MODE_POST_EXP` at idle: queue-end `transition_to_manual` only covers the LAST shot's `devices_in_use` (`blacs/blacs/experiment_queue.py:654-658`). Stranded tab = poll frozen AND `program_device` dead (it's `MODE_MANUAL`-only, `device_base_class.py:419`). Escapes: pause the queue (sweeps POST_EXP tabs to manual, `experiment_queue.py:539-543`) or include the device in a later shot. Latent for rastering (in every shot) — real for any device that's sometimes omitted.

## Cost / cautions

- Two extra REQ-REP round trips per device land in the inter-shot gap. Worker is single-threaded: a hung GUI holding a poll up to `DEFAULT_TIMEOUT_MS = 5000` (`RemoteControl/blacs_workers.py:34`) would delay the next shot's `transition_to_buffered` behind it. This is the only real argument against. **CORRECTION (blacs-expert audit 2026-08-05): the worst case is N×5 s per device, not ≤5 s** — `check_remote_values` loops every output channel and short-circuits only on a hard `None` (`blacs_workers.py:589-597`): Rastering 2→10 s, LaserLock 3→15 s, BigSky 9→45 s when each reply lands just under timeout. Under the queue manager's `timeout_limit = 300` this stretches the gap rather than breaking the queue.
- **Not an incident fix**: a fresher echo makes an abort replay MORE likely to re-assert a just-measured edge position, not less. Decide on its own merits (fresher panel between shots, un-freezing stranded tabs).

## Verify after landing

Restart BLACS. Queue 3+ shots; grep BLACS.log for `check_remote_values` timing — confirm polls now land in the inter-shot gap too. Confirm shots aren't delayed (compare `PERF transition_to_buffered` timestamps against a pre-change queue).
