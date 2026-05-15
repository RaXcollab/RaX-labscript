---
name: Qt PreciseTimer is wrong for the main GUI thread on Windows
description: Default to Qt.CoarseTimer for any QTimer that drives heavy work on the Qt main thread; reserve PreciseTimer for worker QThreads and hardware-sync loops
type: feedback
originSessionId: 9981ffe9-0743-48cc-8f63-b03c5f10ca71
---
Default to `Qt.CoarseTimer` for any `QTimer` whose `timeout` slot does heavy work on the Qt main GUI thread. Reserve `Qt.PreciseTimer` for worker `QThread` event loops and hardware-sync loops where missing a tick has hardware consequences.

**Why:** On Windows, `Qt.PreciseTimer` is backed by the Multimedia Timer API (`timeSetEvent` + `timeBeginPeriod(1)`), which fires events from a separate kernel thread on a 1 ms-resolution heartbeat and posts them into the target thread's message queue without the natural rate-limiting that `WM_TIMER`/`SetTimer` has. Combined with heavy per-frame work and an unthrottled producer thread (e.g. EcoQoS-off, elevated priority) contending the GIL, paint/input event processing starves and Windows marks the window "Not Responding". This bit us 2026-05-06 in `GUIs/HF_Locking/main_wlm.py` — switching `_gui_timer_fast` from CoarseTimer to PreciseTimer (paired with EcoQoS opt-out + ABOVE_NORMAL priority) froze the GUI at launch. Reverting the single timer-type line fixed it. Note: Qt docs assert both timer types coalesce late `timeout()` emissions, so the mechanism is *not* "PreciseTimer fails to coalesce" — it is the message-pump backpressure difference between the multimedia-timer backend and `WM_TIMER`.

**How to apply:**
- For Qt main-thread `QTimer`s driving plot updates, label refresh, status panels, etc. → `Qt.CoarseTimer`. The ±5-15 ms jitter is invisible at human-perceived rates (≤30 Hz).
- For worker `QThread` event loops (no Windows message pump exposure) and for tight hardware-sync loops → `Qt.PreciseTimer` is fine and often correct.
- If main-thread plot smoothness ever actually matters (e.g. visible cycle-shift wrap stutter), the correct knob is **per-frame work**, not timer precision: decimate plot buffers (1-3k → ~100 visible points), only call `setData()` on changed channels, set `useOpenGL=True` on PlotWidget. These let CoarseTimer hit its budget reliably.
- Rule applies to PyQt5 on Windows specifically; Qt6 / non-Windows backends may differ but the safe default is the same.
