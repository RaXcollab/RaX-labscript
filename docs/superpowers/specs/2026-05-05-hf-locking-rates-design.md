# HF_Locking Refresh Rate Audit & Rebalance

**Date:** 2026-05-05
**Status:** Design — pending implementation
**Scope:** `GUIs/HF_Locking/` only

## Context

This session addressed Windows focus-throttling on the HighFinesse wavemeter GUI
(EcoQoS opt-out, priority demotion `HIGH→ABOVE_NORMAL`, per-process `powercfg`
rules for both `wlm_ws7.exe` and the conda Python interpreter). With those
fixes in place, the user asked whether the GUI's internal refresh/poll rates
themselves are well-balanced.

The audit examined every continuous rate against the WLM's actual data delivery
cadence (~5 Hz per channel, ~40 Hz aggregate across 8 channels). All
producer/consumer pairs are sane *except one*: the GUI slow timer at 500 ms
(2 Hz) consumes from a producer (worker slow at 1000 ms / 1 Hz) — every other
GUI-slow tick redraws the same labels. Separately, the GUI fast timer uses
`Qt::CoarseTimer`, which on Windows lands frames with 5-15 ms peak-to-peak
jitter at the 33 ms target — visible at the cycle-shift wrap boundary on
pyqtgraph plots, especially when the lab PC is under contention.

## Decision

Two small code edits to `main_wlm.py` and one new reference document:

1. **GUI slow rate**: `GUI_SLOW_MS` 500 → 1000. Aligns the GUI slow producer
   (worker @ 1 Hz) with its consumer.

2. **GUI fast timer type**: `Qt::CoarseTimer` → `Qt::PreciseTimer` on
   `_gui_timer_fast`. Tightens the 33 ms cadence from ±5-15 ms jitter to ±1 ms.
   Worker fast already uses `PreciseTimer`; this brings the two timers into
   consistent precision.

3. **Reference doc**: create `docs/hf-locking-rates.md` documenting every rate
   in the GUI (worker fast/slow, GUI fast/slow, ZMQ PUB, lock-wait poll,
   pending guard, diagnostic budgets), its purpose, the constraint that pins
   it, and why it has the value it does.

Rates explicitly *not* changing, with rationale recorded in the doc:

- Worker fast 20 ms (50 Hz) — slightly faster than aggregate WLM data rate
  (~40 Hz); benefit is bounded capture latency. Original `# matches WLM
  switcher cycle` comment encodes a defensible choice. CPU cost ~1-2 ms/sec.
- ZMQ PUB 100 ms (10 Hz) — sufficient for human-paced BLACS monitor display.
- Lock-wait inner poll 25 ms — produces 125 ms minimum lock declaration with
  the existing `LOCK_CONSECUTIVE = 5` × stale-skip logic (which actually
  requires 5 fresh measurements, so real lock latency is ~1 s at 5 Hz/channel
  data; well-matched and physically meaningful).

## Files Changed

- `GUIs/HF_Locking/main_wlm.py` — 2 lines (one constant, one timer-type call).
- `docs/hf-locking-rates.md` — new file, ~80-120 lines.

## Verification

1. Relaunch `python main_wlm.py`. Confirm normal startup (priority + EcoQoS
   logs unchanged).
2. Watch a channel plot for ~30 s with the lab PC otherwise loaded
   (e.g. with BLACS or lyse running). Plot scroll should look uniformly
   smooth at 30 Hz; the cycle-shift wrap boundary should not visibly stutter.
3. Confirm status panel labels (T, P, setpoints) still update — they will
   now redraw at 1 Hz instead of 2 Hz, which is invisible to a human
   observer but matches the underlying data rate.
4. No regression check: BLACS-side `LaserLockDevice` should still receive
   ZMQ updates and be able to lock a channel via setpoint write.

## Out of Scope

- Worker fast rate (justified, no change).
- ZMQ PUB rate (justified, no change).
- Lock-wait timing (justified, no change).
- `main_wlm_wide.py` (incomplete variant, not production).
- Auto-load rule for the new reference doc (`.claude/rules/ref-*.md`) — can
  be added later if it proves useful when editing `GUIs/HF_Locking/`.
