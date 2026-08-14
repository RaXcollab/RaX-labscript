---
paths:
  - "userlib/user_devices/**"
  - "blacs/**"
---

# Per-Shot Lifecycle & Error-Handling (fork-specific, load-bearing)

## Per-Shot Lifecycle

- **Queued-shot lifecycle:** `transition_to_buffered → start_run → post_experiment` per shot. **No `transition_to_manual` between queued shots.** T2M runs only at queue-end, abort, or pause.
- **Per-shot teardown belongs in `post_experiment`**, NOT `transition_to_manual`. Reset state, restore latched channels, snapshot final monitor values here.
- **Never create or write `/data` before the shot completes** (e.g. in `transition_to_buffered`). `/data`'s presence is the queue manager's "shot has been run" marker; the queue manager creates it after the run and before dispatching `post_experiment` (grep `create_group('data')` in `blacs/blacs/experiment_queue.py`). Per-shot h5 writes go in `post_experiment` (2026-08-02, RasteringDevice incident).
- Worker classes without `post_experiment` trigger a ~80 ms back-compat probe per shot — implement the hook to skip the probe.
- Fork-only MODE flags: `MODE_TRANSITION_TO_POST_EXP=16`, `MODE_POST_EXP=32` (defined in `blacs/blacs/tab_base_classes.py`). Allowed-modes lists on `@define_state` callbacks must include POST_EXP if the callback should fire between queued shots.

## Error-Handling Change Protocol

- **Changed error/timeout semantics → sweep every caller.** Grep all callers of the changed primitive and trace each operating mode (manual snap, continuous, buffered grab) end-to-end before declaring done. Fixing one path does not fix the class (2026-07: 214-timeout retry fixed for buffered `grab_multiple`; unswept `snap`/`continuous_loop` siblings failed the next day).
- **Audit scope = blast radius, not diff size.** A one-line config change that interacts with changed error semantics still gets the `blacs-expert` audit.
- **Known gaps are decisions, not footnotes.** Operator-facing + cheap (≲10 lines) → fix in the same pass, or get an explicit defer from the user. Deferred → record as a tracked open item, never only prose in a summary.
- **Verify all modes after camera/acquisition changes**: manual snap, continuous view, AND a queued shot — not just the test shot.

## NI_DAQmx Latched-Lines Invariant

- `device_properties['latched_lines']` (set via `set_property` in connection table) channels hold their first-shot value across queued shots (e.g. `LIF_shutter`).
- **Three-layer restore**: `initial_values → cached_final_values → initial_values for latched-only`, applied in BOTH `post_experiment` (queued path) AND `transition_to_manual` (queue-end / abort path). See `docs/blacs-device-patterns.md` "Latched Digital Output Pattern".
- `_ensure_manual_DO_task()` creates a DO-only task (no AO, to avoid glitching analog) when needed between queued shots.
- Mechanism lives inside the shared `NI_DAQmxOutputWorker` — guard device-specific code with `if self._latched_lines:`.
