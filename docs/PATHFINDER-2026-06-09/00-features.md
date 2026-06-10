# Rastering Subsystem — Feature Inventory (Pathfinder 2026-06-09)

Boundaries set by the orchestrator from the import graph, naming, and prior
deep exploration (Explore agents A/B + the F2 design pass). The live operator
GUI runs from `GUIs/rastering` on `main`; all analysis is read-only.

## Scope

- **GUI** (`GUIs/rastering/`, branch `main`): `raster_controller.py`,
  `raster_paths.py`, `ui.py`, `main_rastering.py`, `camera.py`,
  `camera_settings_dock.py`, `hardware.py`, `config.py`.
- **BLACS device** (`userlib/user_devices/RasteringDevice/`):
  `labscript_devices.py`, `blacs_tabs.py`, `blacs_workers.py`,
  `register_classes.py`.
- **ZMQ bridge**: GUI REQ-REP server (`tcp:55535`) + PUB-SUB (`55536`) ↔ BLACS
  `RasteringWorker(RemoteControlWorker)`.

## Features

| # | Feature | Entry point(s) | Core files | Purpose |
|---|---------|----------------|------------|---------|
| F1 | **Path generation** | `iter_path_from_spec(spec)` | `raster_paths.py` | Lazy generators (square X/Y serpentine, inward spiral, convex-hull fill) yielding `(x,y)` target points; `collect_points` materializes. |
| F2 | **Motor command queue & execution** | `request_move_target(x,y)` (`raster_controller.py:366`) | `raster_controller.py` (MotorCommand/queue/worker thread), `hardware.py` (KCube/Kinesis) | Priority-queue of `MotorCommand`s drained by a worker thread that applies calibration, bounds-checks, and drives the KCube motors; emits position signals. |
| F3 | **Calibration (affine)** | `AffineCalibration.target_to_motor` (`:160`), `CalibrationSession` (`:258`) | `raster_controller.py`, `ui.py` (calibrate mode), `calibration_data.json` | Least-squares affine (M,b) from ≥3 click→motor pairs; maps plot/target space ↔ motor units; persisted to JSON. |
| F4 | **Raster run-loop & stepping + Automatic Controls** | `start_raster` (`:896`), `raster_step` (`:919`); UI `_start_raster` (`ui.py:1003`), `_step_raster` (`ui.py:676`) | `raster_controller.py`, `ui.py` | Continuous serpentine run-loop (Qt signal chain + QTimer delay) and single-step mode over the one-shot `_raster_iter`; the Automatic Controls tab buttons. |
| F5 | **ZMQ transport & BLACS bridge** | GUI `_zmq_loop`; BLACS `RasteringWorker` | `raster_controller.py` (`_zmq_loop`), `RasteringDevice/blacs_tabs.py`, `blacs_workers.py`, `labscript_devices.py`, `register_classes.py` | v1 JSON REQ-REP (CHECK_VALUE/PROGRAM_VALUE on `laser_raster_x_coord`, `laser_raster_y_coord`, `arm_raster`, `move_to_next`) + PUB monitor topics. BLACS sends `move_to_next` per shot when Raster Mode is ticked. |
| F6 | **Camera pipeline** | `CameraThread` run loop; dock commits | `camera.py`, `camera_settings_dock.py`, `ui.py` (display), `config.py` | IDS uEye (pyueye) frame grab → display on the pyqtgraph view with the live target marker. *(Parked `feat/spinnaker-gige` replaces this with rotpy/Spinnaker.)* |

## Cross-cutting concerns to probe in Phase 2 (duplication)

- Coordinate transforms: `ui.py:_on_plot_click` vs `AffineCalibration.target_to_motor` vs the move primitives.
- Parallel motor-move paths: `request_move_target` vs `raster_step` vs `_enqueue_next_raster_point` vs the ZMQ `PROGRAM_VALUE` handler.
- "Current position" caches: `_last_target_xy`/`_last_motor_xy` vs PUB monitor cache vs `current_target_marker` vs the move-to spinboxes.
- Bounds: controller `_execute` `target_bounds`/`motor_bounds` vs `ui._display_bounds` vs the commented-out `set_target_bounds()`.
- Path materialization: preview `collect_points` vs run-loop one-shot iterator.

## Notes feeding the parked-branch decision (Phase 4 of the session plan)

- **F6** is the only feature the camera migration (`feat/spinnaker-gige`) touches.
- **F5** is the only feature the transport rewrite (`zmq-v2-port`) touches.
- The "go-to-arbitrary-site" feature lands in **F4** (+ small F3 reuse).
