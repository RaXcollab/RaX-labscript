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

## Worker Paths

- Custom devices: `"user_devices.RemoteControl.blacs_workers.RemoteControlWorker"`
- NOT `"labscript_devices.RemoteControl..."` — wrong module

## Hardware Change Scoping

- Scope modifications to EXACTLY the channels/lines/devices requested — never expand to "all outputs"
- NI_DAQmx DO writes are per-port (all lines in a port written atomically) — changing one line requires re-sending all lines on that port
- When overriding `transition_to_buffered` or `program_manual`, verify the change only affects the intended channels

## Cross-Device Impact

- **`NI_DAQmxOutputWorker` is shared by ALL NI devices** (6361, 6535). When modifying it, trace impact on EVERY device in the connection table
- **`NI_DAQmxAcquisitionWorker`** is separate but runs on NI devices with AI channels
- For BLACS worker changes: ALWAYS have `blacs-expert` audit. For safety-critical changes, cross-audit with both `blacs-expert` AND `amo-expert`
- When making a method idempotent (adding cleanup at top), audit the FIRST call path — attributes may not exist yet during `init()`

## Per-Shot Lifecycle (fork-specific, load-bearing)

- **Queued-shot lifecycle:** `transition_to_buffered → start_run → post_experiment` per shot. **No `transition_to_manual` between queued shots.** T2M runs only at queue-end, abort, or pause.
- **Per-shot teardown belongs in `post_experiment`**, NOT `transition_to_manual`. Reset state, restore latched channels, snapshot final monitor values here.
- Worker classes without `post_experiment` trigger a ~80 ms back-compat probe per shot — implement the hook to skip the probe.
- Fork-only MODE flags: `MODE_TRANSITION_TO_POST_EXP=16`, `MODE_POST_EXP=32` (per `blacs/blacs/tab_base_classes.py:64`). Allowed-modes lists on `@define_state` callbacks must include POST_EXP if the callback should fire between queued shots.

## NI_DAQmx Latched-Lines Invariant

- `device_properties['latched_lines']` (set via `set_property` in connection table) channels hold their first-shot value across queued shots (e.g. `LIF_shutter`).
- **Three-layer restore**: `initial_values → cached_final_values → initial_values for latched-only`, applied in BOTH `post_experiment` (queued path) AND `transition_to_manual` (queue-end / abort path). See `docs/blacs-device-patterns.md` "Latched Digital Output Pattern".
- `_ensure_manual_DO_task()` creates a DO-only task (no AO, to avoid glitching analog) when needed between queued shots.
- Mechanism lives inside the shared `NI_DAQmxOutputWorker` — guard device-specific code with `if self._latched_lines:`.