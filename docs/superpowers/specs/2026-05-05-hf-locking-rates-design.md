# HF_Locking Refresh Rate Audit & Rebalance

**Date:** 2026-05-05
**Status:** Implemented 2026-05-05; **GUI fast PreciseTimer reverted 2026-05-06** (see Follow-up).
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

## Follow-up — 2026-05-06: GUI fast PreciseTimer reverted

Decision (2) above was **wrong**. After landing on 2026-05-05, the GUI froze
at launch on Win11 — main window painted via `show()` but the main thread
never pumped events; clicking surfaced "Not Responding". User-confirmed
evidence: both `[PRIORITY]` and `[POWER]` startup lines printed (so the
EcoQoS opt-out and priority change ran fine), no `_RestoreDialog` appeared
(rules out the modal hypothesis), regression appeared immediately after the
commit.

**Bisection:** reverted only the `Qt::CoarseTimer → Qt::PreciseTimer`
change at `main_wlm.py:236`. GUI launched and responded normally.
Decisions (1) and (3) — `GUI_SLOW_MS` 500 → 1000 and the rate-inventory
doc — kept; the EcoQoS opt-out and priority demotion from the parent
focus-throttling commit also kept.

**Mechanism (best-supported, not bench-verified):** on Windows, Qt's
`PreciseTimer` uses the Multimedia Timer API (`timeSetEvent`) which fires
events from a separate kernel thread on a 1 ms-resolution heartbeat
(`timeBeginPeriod(1)`), posting into the GUI message queue without the
natural rate-limiting that `WM_TIMER`/`SetTimer` has. The GUI's
`_refresh_gui_fast` triggers 8 channels of `pyqtgraph.setData` updates per
frame (16-48k point updates), plausibly >33 ms per call. Combined with
the unthrottled (EcoQoS-off, ABOVE_NORMAL) worker thread contending the
GIL at 50 Hz, paint/input events get starved enough for Windows to mark
the window unresponsive. (Note: Qt docs assert both timer types coalesce
late `timeout()` emissions, so coalescing-failure is not the mechanism;
the message-pump backpressure differs by backend.)

**Lesson — GUI-thread timer-type rule (Windows):**
- Default `CoarseTimer` for any QTimer that triggers heavy work on the
  Qt main thread.
- Reserve `PreciseTimer` for worker QThreads and hardware-sync loops
  where missing a tick has hardware consequences.
- The PreciseTimer benefit (cycle-shift wrap stutter at ±1 ms vs ±5-15 ms
  jitter) is a one-shot ~14 ms visual hiccup once per sweep period — not
  worth the multimedia-timer fragility.
- If plot smoothness ever actually matters: tune per-frame work
  (decimate buffer, partial updates, `useOpenGL=True`), not timer
  precision.

**Untested sub-hypotheses (left open):**
- Whether `PreciseTimer` alone (without the EcoQoS opt-out / priority
  demotion) would also freeze. The Win11 fix was correct and shipped; the
  PreciseTimer revert is independently the right architectural choice
  regardless.

**Files touched in revert:**
- `GUIs/HF_Locking/main_wlm.py` — 4-line block (rationale comment +
  `setTimerType` call) collapsed back to single `CoarseTimer` line.
- `docs/hf-locking-rates.md` — table row flipped, rationale paragraph
  rewritten with the lesson.
- `notes/2026-05-05_HF-Locking-Focus-Throttling-and-Rate-Audit.html` —
  appended a "Regression & Resolution" section.
