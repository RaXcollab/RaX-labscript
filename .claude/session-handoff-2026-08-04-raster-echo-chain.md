# Handoff: Rastering front-panel echo chain (refused-write mechanism)

**Status: mechanism fully verified 2026-08-04 (blacs-expert, file:line evidence). Incident-class fixes LANDED — this doc is the context for anything that still comes back `motor_move_failed` on a front-panel push.**

## The core fact

In a session where nobody touches the coord spinboxes, **the front-panel x/y are not commands — they are measured motor positions, echoed back**. BLACS re-asserts them as commands on specific triggers. Treat every `program_manual` coord write as "replay a measurement", not "operator intent".

## The chain (all verified file:line)

1. GUI answers `CHECK_VALUE` with `_last_target_xy` — a fresh encoder read passed through the **inverse** calibration (`GUIs/rastering/raster_controller.py:602-624`; cache written post-move at `:1997-2000`). Measured, pixel-frame.
2. Worker poll: `check_remote_values` → `{connection: float}` (`userlib/user_devices/RemoteControl/blacs_workers.py:580-597`), every 5 s (`RemoteControl/blacs_tabs.py:357-359`).
3. Tab writes it into the AO widget with `set_value(value, program=False)` (`RasteringDevice/blacs_tabs.py:299-306`). **`program=False` skips only the re-program — `AO._current_value` and `_settings['base_value']` ARE overwritten** (`blacs/blacs/output_classes.py:362-386`). The echo also persists into saved tab state.
4. `get_front_panel_values()` returns exactly `_current_value` (`blacs/blacs/device_base_class.py:400-401`).
5. Buffered shots program the GUI over ZMQ and **never write the panel back** (`RasteringWorker.transition_to_buffered` returns `{}` → no final-value writeback). So over a raster, the panel converges to the raster's last measured point — travel edges included.
6. Replay triggers — `program_device()` sends the **whole panel**, unfiltered: queue abort (`device_base_class.py:710-712`, `:726-729`), tab startup (`:66-72`), and any single spinbox edit (re-sends the untouched sibling too, `output_classes.py:374-376`).

## Why the replay gets refused

The affine calibration has cross-terms: the motor-x command computed from pixel-x depends on the **current y**. A position measured at the x travel floor with y=y1, replayed after y moved to y2, maps `~2.5e-5 × Δy_px` mm past the floor (≤~5 µm full-field with the 2026-07-20 fit; the 12:29 incident was 1.2 µm).

## Refusal taxonomy + current handling (post-fix)

| Cause | Outcome now |
|---|---|
| Echo-replay of measured edge position (incident) | **succeeds** — 10 µm edge clamp (`clamp_to_bounds`, rastering `6baf4fb`) |
| Stale-partner echo (≤5 µm cross-term) | **succeeds** (clamp) |
| Operator types beyond travel (panel accepts 0-25, travel 0-12) | typed `Rejected: motor out of bounds` → log warning, sibling still sent |
| Motor disconnected / Kinesis error | `motor_move_failed` (retryable) → log warning |
| GUI closed / timeout | warn-and-continue (`program_manual` courtesy-write policy, parent `f9be922`) |
| Startup before first fetch | no write at all (`_initial_fetch_done` guard) |
| **Sequential-pair excursion**: x-then-y single-axis moves physically visit `(x_new, y_old)`; if THAT composite is out of travel, x is refused even when both endpoints are legal | **NOT fixed by clamp** — fixed by the atomic-pair change (see `session-handoff-2026-08-04-atomic-xy-pair.md`) |

Key policy split: `program_manual` = courtesy write (warn-and-continue via `RasteringWorker._on_program_manual_error`); `transition_to_buffered` = strict raise (fails the shot). A raised worker exception is STICKY (`tab.error_message`) and silently blocks `transition_device_to_buffered` for all later shots until the operator clicks ✕ (`blacs/blacs/experiment_queue.py:495-501`).

## Ceilings / watch items

- `MOTOR_EDGE_CLAMP_MM = 0.010` is sized to the CURRENT calibration's cross-terms. **Re-check after any recalibration** — a fit with larger cross-terms re-opens edge rejections.
- Torn echo pairs: x and y are polled in separate REQ-REPs; a raster step between replies fabricates a panel pair that was never a real position. Killed by the atomic-pair change.

## Units direction (user-decided 2026-08-04)

- **Motor units are FIXED** (Z912 travel 0-12 mm); **pixel units vary with every calibration re-fit**. Any bound expressed in pixels is implicitly tied to one calibration and goes stale at the next fit.
- **Do NOT tie connection-table bounds to a specific calibration** — a pixel-range limit like "(0, 5000)" is derived from the 2026-07-20 fit and is exactly the coupling to avoid.
- **Future work: frame-explicit coordinate communication** — the BLACS↔GUI protocol should support pixel OR motor coordinates on the wire (frame-tagged values). Once motor-frame communication exists, connection-table channels can legitimately declare motor units with the fixed (0, 12) limits — stable across recalibrations. Until then, the GUI-side `motor_bounds` + clamp remain the only calibration-independent enforcement.

## Landed commits

Rastering `main`: `804a8a9` (wrap zmq steps), `9608d72` (fresh partner + wrap all sources), `6baf4fb` (motor_bounds 0-12 mm + units guard + edge clamp). Parent `master`: `11d8525` (program_manual policy hook), `f9be922` (courtesy-write + wrap-native worker). Restart rastering GUI + BLACS together to activate.
