<claude-mem-context>

</claude-mem-context>

# LaserLockDevice

- **No `blacs_workers.py` here — by design.** `LaserLockTab.initialise_workers` wires the BASE `RemoteControlWorker` by string path (`blacs_tabs.py:351`). Only 2 live worker subclasses exist workspace-wide (BigSkyWorker, RasteringWorker) — don't "fix" the missing subclass. String-path wiring is invisible to AST tools (graphify: no edge, deliberately).
