<claude-mem-context>

</claude-mem-context>

# LaserLockDevice

- **No `blacs_workers.py` here — by design.** `LaserLockTab.initialise_workers` wires the BASE `RemoteControlWorker` by string path (`blacs_tabs.py:351`). Only 2 live worker subclasses exist workspace-wide (BigSkyWorker, RasteringWorker) — don't "fix" the missing subclass. String-path wiring is invisible to AST tools (graphify: no edge, deliberately).

## Operator note

LaserLock keeps the base `RemoteControlWorker`'s STRICT `_on_program_manual_error` (no courtesy-write override, by decision). A refused front-panel write raises, which sets a **STICKY** `tab.error_message` on the LaserLock tab — a red error banner. `experiment_queue.py:495-501` refuses `transition_device_to_buffered` while that banner is set, so the queue silently stalls (accepts shots, never runs them) until the operator dismisses the LaserLock/HF tab's error with its **X button** (or restarts BLACS). **Dismiss any red LaserLock/HF error banner before re-queueing shots.**
