# HF_Locking Refresh Rates

Reference for every continuous rate, polling cadence, and timing constant in
the HighFinesse wavemeter GUI (`GUIs/HF_Locking/`). Values reflect the state
of the codebase as of 2026-05-05.

## The data-rate constraint

Every downstream rate in this GUI is bounded by the WLM's measurement
delivery cadence. The WS7 fiber switcher cycles through 8 channels with
~25 ms exposure each:

- **Per-channel update rate**: ~5 Hz (one fresh value every ~200 ms)
- **Aggregate update rate**: ~40 Hz (a fresh value lands somewhere among
  the 8 channels every ~25 ms)

`GetFrequencyNum(port)` is a non-blocking cache read — calls between
WLM updates return `wlmConst.InfNothingChanged` (-7), which the worker
treats as a sentinel and which `_wait_for_lock` uses to reset its
consecutive counter (so `LOCK_CONSECUTIVE` requires *fresh* in-tolerance
measurements, not just repeated cache hits).

## Rate inventory

### Continuous rates

| Rate | Value | Hz | Source | Code |
|---|---|---|---|---|
| Worker hardware poll, fast | 20 ms | 50 Hz | DLL frequency reads, all 8 channels | `workers.py:13`, `PreciseTimer` |
| Worker hardware poll, slow | 1000 ms | 1 Hz | T, P, bounds, setpoints | `workers.py:14`, `CoarseTimer` |
| GUI render, fast | 33 ms | ~30 Hz | plots + frequency labels | `main_wlm.py:72`, `CoarseTimer` |
| GUI render, slow | 1000 ms | 1 Hz | status panel, T/P labels | `main_wlm.py:73`, `CoarseTimer` |
| ZMQ PUB broadcast | 100 ms | 10 Hz | frequency + heartbeat to BLACS | `workers.py:19` |

Both fast loops have re-entrancy guards (`_busy_fast` in worker,
`_busy_gui_fast` in GUI). If a previous tick is still running, the next is
skipped silently.

### Event-driven / one-shot timing

| Constant | Value | Purpose | Code |
|---|---|---|---|
| Lock-wait inner poll | 25 ms (40 Hz) | Polls `SharedState` during buffered-shot block | `workers.py:620,626,640` |
| `LOCK_TIMEOUT_S` | 60 s | Max wait for setpoint convergence | `workers.py:24` |
| `LOCK_CONSECUTIVE` | 5 | Fresh in-tolerance reads required to declare lock | `workers.py:25` |
| `LOCK_TOLERANCE` | 5e-6 THz = **5 MHz** default | Convergence tolerance; per-port overrides in `LOCK_TOLERANCE_BY_PORT` (TiSa_1 ch1 = **1 MHz**) via `lock_tolerance(port)` | `workers.py:20-32` |
| `_PENDING_GUARD_S` | 1.0 s | Suppresses local-input clobber after "Set F" click | `display.py:101` |

### Diagnostic budgets (only active if `diagnostics.ENABLED=True`)

| Threshold | Value | Triggers |
|---|---|---|
| `WARN_POLL_FAST_MS` | 40 ms | warns if worker fast-poll exceeds 2× budget |
| `WARN_GUI_UPDATE_MS` | 20 ms | warns if GUI render exceeds 60% of GUI fast budget |
| `WARN_QUEUE_LATENCY_MS` | 50 ms | warns if a cross-thread signal sat queued |

## Rationale (why each value)

**Worker fast — 20 ms (50 Hz)**: slightly faster than the WLM's aggregate
data rate (~40 Hz). ~90 % of DLL calls hit the `InfNothingChanged` cache
and cost only a few µs each (~1-2 ms of CPU per second total). The benefit
is bounded capture latency: when a fresh value lands, the worker reads it
within 20 ms. Could relax to 25-33 ms without losing data; was kept at
20 ms to maintain tight latency for lock detection and ZMQ broadcasts.
Comment in source: `# matches WLM switcher cycle (~20-50ms)`.

**Worker slow — 1 Hz**: T, P, bounds, setpoints all change on
human-ish timescales. 1 Hz is the right physical match.

**GUI fast — 30 Hz (33 ms)**: pyqtgraph community baseline; below this
the cycle-shift plot scroll feels choppy. Going faster (60 Hz) would
double CPU with no perceptual benefit — data only arrives at ~5 Hz/channel
so 60 Hz frames are mostly redrawing the same staircase. Uses
**`CoarseTimer`**, not `PreciseTimer`. Briefly switched to `PreciseTimer`
on 2026-05-05 to tighten the cycle-shift wrap-boundary stutter; this caused
a complete GUI freeze at launch (Windows "Not Responding") and was reverted
2026-05-06. On Windows, `PreciseTimer` uses the Multimedia Timer API
(`timeSetEvent` + `timeBeginPeriod(1)`), which posts events from a separate
kernel thread without the natural rate-limiting that `WM_TIMER` has;
combined with heavy per-frame work (8 channels × pyqtgraph `setData`,
plausibly >33 ms total) and the unthrottled (EcoQoS-off, ABOVE_NORMAL)
worker thread contending the GIL at 50 Hz, the GUI message queue starves
paint/input events. **Rule of thumb**: on Windows, default `CoarseTimer`
for any QTimer driving work on the main GUI thread; reserve `PreciseTimer`
for worker QThreads and hardware-sync loops. If wrap-boundary smoothness
ever actually matters, the right knob is per-frame work (decimate plot
buffers to ~100 visible points, only `setData` on changed channels,
`useOpenGL=True`) — not timer precision.

**GUI slow — 1 Hz**: matched to its producer (worker slow, 1 Hz). Was
2 Hz prior to 2026-05-05; that meant every other GUI-slow tick redrew the
same labels.

**ZMQ PUB — 10 Hz**: BLACS-side `LaserLockDevice` displays values at
human-pace; 10 Hz is responsive to a watcher and gives 2× margin over the
per-channel 5 Hz update rate. Higher rates (20-50 Hz) are possible but
provide no perceptible benefit on the BLACS side and add network/CPU.

**Lock-wait inner poll — 25 ms with `LOCK_CONSECUTIVE = 5`**: the
inner loop resets `consecutive` on stale reads (`InfNothingChanged`),
so 5 consecutive in-tolerance reads requires 5 *fresh* measurements. At
5 Hz/channel that's a real ~1 s lock-confirmation window — physically
meaningful, robust to transient glitches. The 25 ms poll period bounds
the latency to detect each fresh measurement.

**Pending guard — 1 s**: empirically tuned to cover the worst-case
DLL round-trip + UI feedback after a local "Set F" click. ZMQ-originated
writes intentionally bypass this guard.

## When to revisit

Re-tune if any of these change:

- **WLM exposure setting changes**: longer exposure (>50 ms/channel) drops
  the per-channel data rate below 5 Hz; the worker fast rate could relax
  proportionally, and `LOCK_CONSECUTIVE` × poll-period determines lock
  declaration time.
- **Channel count changes**: fewer active channels means the aggregate
  data rate drops; same trigger as above.
- **EcoQoS / power throttling re-enabled**: worker rate jitter would
  return; reconsider all `PreciseTimer` choices.
- **Diagnostics enabled in production**: if `WARN_POLL_FAST_MS` fires
  routinely, the DLL is taking longer than expected — investigate the
  WS7 server before lowering the poll rate.

## Related

- Code: `GUIs/HF_Locking/main_wlm.py`, `workers.py`, `diagnostics.py`,
  `display.py`
- Project notes: `GUIs/HF_Locking/CLAUDE.md` (threading model)
- Design history: `docs/superpowers/specs/2026-05-05-hf-locking-rates-design.md`
