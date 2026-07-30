# Duplication Report — Rastering Subsystem (Pathfinder 2026-06-09)

16 duplications found (within-feature + cross-feature). Each cites ≥2
`file:line` locations. Split into **accidental** (worth consolidating) and
**legitimate specialization** (leave, or optional tidy).

## A. Accidental duplication — consolidate

### A1. Raster stepping command paths (HIGH — touches the stepping feature)
- `raster_controller.py:919-959` (`raster_step`) and `raster_controller.py:1527-1551` (`_enqueue_next_raster_point`) both pull `next(it)`, validate state, and enqueue `MOVE_TARGET` tag `raster_step`. ZMQ `:1757` delegates to `raster_step` (correct).
- **Why diverged:** `raster_step` is the public UI/ZMQ entry (continuous-mode guard + wait/timeout); `_enqueue_next_raster_point` is the QTimer-driven continuous driver. Same iterator-consume + enqueue core.
- **Fix:** extract a shared cursor helper (the F2 plan's `_next_raster_point_locked()`), called by both. **This is Stage 1 of the stepping feature — already planned.**

### A2. Motor-bounds checks duplicated 4× in `_execute` (HIGH — ties to Display Bounds gap)
- `raster_controller.py:1205-1210`, `:1247-1252`, `:1311-1320`, `:1336-1345` — four near-identical `_within_bounds()` guard clauses across MOVE_MOTOR_X_ONLY / MOVE_MOTOR / uncalibrated MOVE_TARGET / calibrated MOVE_TARGET (error text differs by context).
- **Fix:** extract `_validate_and_transform_target(target_xy) -> (motor_xy, MotorResult|None)` doing target-bounds → calibration transform → motor-bounds in one pipeline. **This is the natural home to wire the commented-out `set_target_bounds()`** so Display Bounds finally enforces limits (Phase 3 flagged item) and so F2 goto inherits bounds-checking for free.

### A3–A6. Camera-dock `blockSignals` boilerplate (LOW — likely mooted by Spinnaker)
- A3 AOI slider↔spin sync, 4 methods: `camera_settings_dock.py:403-407,409-412,416-420,422-425`.
- A4 timing-mode (FPS) widget init: `ui.py:415-420` & `:558-563`.
- A5 rotation/flip widget sync: `ui.py:509-517` & `:1340-1348`.
- A6 spinbox `blockSignals+setValue` (backlash/home): `ui.py:1142-1146,1155-1159,1223-1227`.
- **Fix:** one `_set_widget_silent(w, value)` / `_set_spinbox_silent` helper. **NOTE:** A3 (and much of the dock) is **rewritten on `feat/spinnaker-gige`** — consolidate only after the camera-branch decision, or it's wasted work.

### A7. Rotation k↔index mapping defined inline 4×
- `camera_settings_dock.py:438`, `ui.py:283,508,1339` — `{0:0,1:-1,2:2,3:1}` and its inverse.
- **Fix:** one shared `_ROTATION_INDEX_TO_K` constant + inverse. (Also camera-adjacent.)

### A8. `[0,1]` clamp idiom 3×
- `camera_settings_dock.py:346,355`, `ui.py:1508` — `max(0.0,min(1.0,x))`.
- **Fix:** one `clamp_frac()` util or `np.clip`.

## B. Legitimate specialization — leave (optional tidy noted)

- **target_to_motor in UI vs `_execute`** (`ui.py:257-258` vs `raster_controller.py:1224,1261,1333`) — UI needs immediate spinbox feedback; `_execute` transforms at dispatch. Distinct timing.
- **Position caches `_last_motor_xy`/`_last_target_xy`** across branches (`:1130-1137,1221-1226,1258-1263,1354-1356,1413-1415`) — feed jog/single-axis ops; signals drive UI. Optional: `_update_position_cache(mx,my)` helper.
- **`_within_bounds` (controller) vs `within_bounds` (raster_paths)** (`raster_controller.py:1051-1056` vs `raster_paths.py:40-44`) — planning-time vs enforcement-time. Optional: import the paths one as single source.
- **Motor reads in 3 contexts** (`:1126-1138,1121-1124,1199,1058-1066`) — calibrated read vs bare read vs telemetry poll. Optional: `_read_motor_position_and_sync(apply_calibration)`.
- **`_raster_preview_pts` vs `collect_points`** (`ui.py:68-70,958-965` vs `raster_paths.py:73-79`) — UI filter cache vs path util. Legitimate.
- **Config/persistence scattered** (`config.py:71,122,145`, `raster_controller.py:48-82`, `camera.py:773-975`) — app paths vs calibration breadcrumb vs uEye `.ini`. Optional: a `ConfigManager` for path resolution only.
- **PUB-SUB cache vs BLACS `_pubsub_cache`** (`raster_controller.py:1620-1625` vs `RasteringDevice/blacs_workers.py:84`) — process-isolation bridge; BLACS caches for shot-record atomicity. Necessary.
- **Target-display 3-step Qt path** (`ui.py:1094,1432-1439`, `raster_controller.py:1415`) — standard emit→dispatch→update.

## Headline

The only accidental duplications worth acting on **now** are **A1** and **A2** — both inside the controller, both directly on the stepping/bounds work already planned. Everything else is either legitimate specialization or camera-dock boilerplate that the parked Spinnaker branch already rewrites.
