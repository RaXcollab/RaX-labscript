# Auto Memory — RaX Labscript Suite

## Workflow Lessons
- **Auto-launch domain agents proactively** — when the user describes hardware behavior, channel types, BLACS internals, or any domain-specific issue, launch blacs-expert/amo-expert/lyse-analysis IMMEDIATELY without being asked. Don't wait for "use agents" — just do it.
- **Agent-aware planning** — plans must explicitly track which claims have been agent-audited and which haven't. Mark each section with audit status. This prevents shipping unvalidated design choices.
- **Ask for the error message FIRST** — narrows search before launching agents
- **When user proposes a fix, validate directly** — read 2-3 files, don't launch broad agents
- **Mixed working tree is normal** — each session commits only its own changes
- **PowerShell paths**: use `.Replace()` not `-replace` (regex breaks on backslashes)
- **Research constraints first** — when asked "can I do X?", check hard limitations before proposing solutions
- **Re-audit after lifecycle discoveries** — when new BLACS lifecycle facts emerge (e.g., post_experiment vs transition_to_manual), re-audit ALL existing changes
- **Audit first-call paths for idempotency** — when adding cleanup/teardown to a method's top, verify attributes exist on the first call from init()
- **Cross-audit as default** — for BLACS safety-critical changes, have blacs-expert audit everything amo-expert checked, and vice versa
- **Audit external GUI compound functions** — when auditing RemoteControl devices, also audit the external GUI's compound command sequences (e.g., startWarmup, startLaser). The GUI is the serial interface; mode-sequencing bugs there cause real hardware issues that BLACS-side audits won't catch.
- **Subagent context: use `skills:` preloading** — subagents don't inherit parent skills or auto-memory. Use `skills:` frontmatter to inject shared context (official pattern). Fallback: pass full auto-memory path (`C:\Users\radmo\.claude\projects\c--Users-radmo-labscript-suite\memory\`) in the prompt.
- **Cross-repo hardware command consistency** — when fixing hardware command bugs in a BLACS device class, always check the corresponding external GUI for the same bug. The External GUI Registry in CLAUDE.md lists GUI codebases.
- **Verify command values against hardware docs, not existing code** — existing code may contain the bug you're trying to fix. When replicating hardware command patterns, check the hardware manual or reference doc first.
- **Google first for hardware/protocol errors** — when encountering errors with hardware communication, serial protocols, or device behavior, do a web search first. We are often not the first to encounter the issue.
- **Don't guess labscript suite behavior** — if unsure how RunManager, BLACS, or other labscript tools behave (scan ordering, expansion modes, shuffle, etc.), say so and ask the user rather than guessing. Our fork may differ from official docs, so the user is the authority. Offer to Google it if needed, but don't present search results as definitive.
- **Research before writing rationale comments in code** — don't ship plausible-sounding guesses as facts. Either verify against vendor docs first, or omit the speculative rationale. Speculative rationale is worse than no rationale: it's load-bearing misinformation embedded in the code. Details: [feedback_research-rationale-not-guess.md](feedback_research-rationale-not-guess.md)
- **Create reference docs when domain knowledge causes bugs** — if a bug was caused by missing physics/hardware knowledge (not a code pattern issue), create a reference doc in `docs/` with an auto-load rule in `.claude/rules/`. Prevents the same class of mistake.
- **Prefer PUB-SUB for monitor reads** — use PUB-SUB cached values (tab monitor callbacks) for reading current device state. Zero latency, no blocking. Use REQ-REP CHECK_VALUE only when guaranteed freshness is needed (e.g., verifying a command took effect). Applies to all RemoteControl devices.
- **Always audit before ExitPlanMode** — don't present plans for approval without blacs-expert/amo-expert audit. Plan agents miss BLACS lifecycle edge cases (stale queued events, thread races) that domain experts catch.
- **For analysis/notebook tasks, prefer action over questions** — use sensible defaults; ask only when truly ambiguous
- **For scan analysis: launch amo-expert + lyse-analysis** — amo-expert for scan structure/globals/experiment design, lyse-analysis for h5 reading/trace utilities
- **Plan mode blocks web tools for subagents** — do web research from main thread during planning, or launch research agents before entering plan mode
- **Monitor context fill** — when conversation is long/complex, proactively suggest "document & clear" (write progress to markdown, /clear, resume). Context accuracy degrades past ~50% fill
- **Do regular introspection sessions** — review what went well/poorly, update context files. Data-driven flywheel: bugs inform improvements
- **Tab-worker shared dict for PUB-SUB cache** — BLACS tab and worker run in the same process. Pass a dict reference via `init_kwargs` to share PUB-SUB cached values with the worker. No extra ZMQ or locking needed (Python GIL protects dict reads/writes). Pattern: tab updates dict in `_on_monitor_value_received`, worker snapshots via `dict(self.cache)`.
- **Lock scope must cover full critical section** — when a lock protects a read-then-act (check flag → consume iterator → enqueue), the lock must cover ALL steps. Releasing between check and act creates a race window, especially with `QTimer.singleShot()` delayed callbacks.
- **Serial disconnect gateway pattern** — route ALL serial I/O through a single `_sendCommand()` method that catches SerialException/OSError and tracks consecutive empty responses. Enables centralized disconnect detection, state reset, and auto-reconnect. Applied to BigSky, should be standard for all serial RemoteControl devices.
- **Proactively audit sibling methods** — when fixing a bug pattern in one method (e.g., cache-before-serial), audit ALL methods in the same class for the same pattern before presenting the fix. Don't wait for the user to ask "does this exist elsewhere?"
- **Cache after serial confirmation** — never update cached hardware state before serial command confirmation. On timeout (None return), leave cache unchanged. Deduplication belongs in the BLACS worker, not the external GUI.

## Jupyter / Analysis Notebooks
- **h5_lock import order is CRITICAL** — `labscript_utils.h5_lock` must be imported before `h5py` anywhere. Never `import h5py` at module top level in analysis modules; defer to inside functions if the import chain hasn't loaded h5_lock yet. See `scan_explorer_widgets.py` for pattern.
- **Widget re-registration on cell re-run** — use module-level `_state` dict with `widgets_created` flag to prevent duplicate `on_click` handlers
- **`%autoreload 3`** (IPython 8+) handles `from X import Y` rebinding — better than manual `importlib.reload`
- **Analysis toolkit**: `scan_plots.py` (ScanAnalysis class), `scan_explorer_widgets.py` (widget layer), details in `memory/analysis-session-2026-03-06.md`

## pyqtgraph Real-Time Plotting
- **Cycle-shift for wrap-around** — store raw elapsed in deque, render as `t % sweep`. Shift old-cycle points by `-sweep` so they appear left of 0. Produces monotonic x-data, enabling `clipToView`.
- **clipToView requires monotonic x-data** — non-monotonic (e.g., raw `% 60`) breaks binary search. Cycle-shift fixes this.
- **`connect` param accepts numpy int32 array** — 0/1 mask controls which points connect. Use for line breaks at wrap boundaries if cycle-shift isn't feasible.
- **Performance checklist**: numpy arrays for setData, pen width=1, clipToView, disable unused auto-range. `skipFiniteCheck` only if no NaN values.
- **Y-autoscale must scope to visible window** — when buffer > visible window (clipToView), iterate only over visible points for min/max, not the full buffer.
- **30-33ms refresh is community standard** for pyqtgraph with 16 curves. Frame-skip counter (`_busy_gui_fast` guard) detects overload.

## Windows ctypes & Qt
- **SetPriorityClass needs HANDLE restype** — `GetCurrentProcess()` returns pseudo-handle (-1), truncated on 64-bit without `restype = ctypes.wintypes.HANDLE`. Use `WinDLL("kernel32", use_last_error=True)`.
- **ABOVE_NORMAL is the priority default** for continuous-polling Python lab tools — HIGH (base 13) risks starving system threads (disk/USB/audio at base 8-12) per Microsoft's "brief time-critical events" guidance. Skip the HIGH-with-fallback dance. NEVER use REALTIME. Details: [feedback_above-normal-priority-default.md](feedback_above-normal-priority-default.md)
- **Win11 has two independent throttling axes** — priority class AND EcoQoS power throttling are separate kernel mechanisms; setting HIGH does NOT disable EcoQoS. For Python tools: in-process `SetProcessInformation(ProcessPowerThrottling, ExecutionSpeed=disabled)`. For closed-source binaries (e.g. `wlm_ws7.exe`): `powercfg /powerthrottling disable /path "<exe>"` from elevated shell, persists in registry. Details: [feedback_win11-dual-throttling.md](feedback_win11-dual-throttling.md)
- **Qt multi-monitor: match by QScreen.name()** — `QApplication.screens()` index order is NOT guaranteed. Use `screen.name() == r"\\.\DISPLAY5"` with primary-screen fallback.
- **Qt main-thread QTimer → CoarseTimer, never PreciseTimer (Windows)** — PreciseTimer uses Multimedia Timer API (separate kernel thread + `timeBeginPeriod(1)`) that bypasses `WM_TIMER` rate-limiting. With heavy per-frame work + unthrottled producer thread, freezes the GUI. Reserve PreciseTimer for worker QThreads / hardware-sync. Tune per-frame work for smoothness, not timer precision. Details: [feedback_qt-precisetimer-gui-thread-windows.md](feedback_qt-precisetimer-gui-thread-windows.md)
- [python3 shim breaks plugin hooks](reference_python3-shim-breaks-plugin-hooks.md) — plugin `hooks.json` that hardcode `python3` were silently dead (Store shim); fixed via `miniconda\python3.exe` copy

## HighFinesse Wavemeter (HF_Locking GUI)
- **WS7 data cadence on this PC** — ~5 Hz per channel, ~40 Hz aggregate across 8 channels at ~25 ms exposure each. `GetFrequencyNum` is non-blocking; returns `InfNothingChanged` (-7) when stale. All downstream rates (worker, GUI, ZMQ PUB, lock-wait) sized against this. Full inventory in `docs/hf-locking-rates.md`. Details: [reference_wlm-data-cadence.md](reference_wlm-data-cadence.md)

@device-internals.md
