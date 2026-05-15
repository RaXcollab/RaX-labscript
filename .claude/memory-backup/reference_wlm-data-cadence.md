---
name: HighFinesse WS7 data cadence on this lab PC
description: ~5 Hz per channel, ~40 Hz aggregate across 8 channels at ~25 ms exposure each. Constraint that all downstream HF_Locking GUI rates must respect.
type: reference
originSessionId: 9db9ac08-3097-4f43-8ecb-8652d9dbc29a
---
The HighFinesse WS7-30 wavemeter on this PC, configured for 8 channels at ~25 ms exposure each, delivers measurements at:

- **Per-channel rate**: ~5 Hz (one fresh value every ~200 ms)
- **Aggregate rate**: ~40 Hz (a fresh value lands somewhere among the 8 channels every ~25 ms)

`GetFrequencyNum(port)` from `wlmData.dll` is a non-blocking cache read — calls between WLM updates return `wlmConst.InfNothingChanged` (-7), which the worker treats as a sentinel. `_wait_for_lock` resets `consecutive=0` on this sentinel, so `LOCK_CONSECUTIVE=5` actually requires 5 *fresh* in-tolerance reads, not 5 cache hits.

**Why this matters:** Every downstream rate in the HF_Locking GUI (worker fast/slow, GUI fast/slow, ZMQ PUB to BLACS, lock-wait inner poll) is bounded by this cadence. Polling faster than the data arrives wastes CPU on stale-cache reads. Polling slower drops fresh values.

**How to apply:**
- Full inventory + per-rate rationale lives in `docs/hf-locking-rates.md`.
- If exposure changes (longer for low-power signals, shorter for fast locking) or active channel count changes, recompute the cadence and re-audit downstream rates. Triggers documented in the doc's "When to revisit" section.
- The 5 Hz / 40 Hz numbers are specific to this lab's WS7 configuration. Other WS-series wavemeters or different exposure / channel-count settings will have different rates.
