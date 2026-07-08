---
paths:
  - "userlib/user_devices/**"
  - "blacs/**"
---

# BLACS Device Conventions

## Qt Thread Safety

- `@define_state` methods resume after `yield` in the mainloop BACKGROUND thread, not the Qt GUI thread
- **USE `inmain()`** for Qt widget calls (setValue, setText, show, hide, setEnabled, etc.)
- **DO NOT USE `with qtlock:`** — it doesn't marshal to the GUI thread; causes Windows access violations
- PUB-SUB daemon threads → use `pyqtSignal` to bridge to the GUI thread

## Hardware Change Scoping

- Scope modifications to EXACTLY the channels/lines/devices requested — never expand to "all outputs"
- NI_DAQmx DO writes are per-port (all lines in a port written atomically) — changing one line requires re-sending all lines on that port

## Cross-Device Impact

- **`NI_DAQmxOutputWorker` is shared by ALL NI devices** (6361, 6535). When modifying it, trace impact on EVERY device in the connection table
- **`NI_DAQmxAcquisitionWorker`** is separate but runs on NI devices with AI channels
- For BLACS worker changes: ALWAYS have `blacs-expert` audit. For safety-critical changes, cross-audit with both `blacs-expert` AND `amo-expert`
- When making a method idempotent (adding cleanup at top), audit the FIRST call path — attributes may not exist yet during `init()`

Lifecycle, latched-lines, and error-handling-change protocol: `.claude/rules/device-lifecycle.md` (same paths — loads alongside this file).