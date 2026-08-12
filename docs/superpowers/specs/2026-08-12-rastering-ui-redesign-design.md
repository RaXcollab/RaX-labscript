# Rastering GUI — UI Redesign (Option A: Run · Pattern · Setup)

**Date:** 2026-08-12
**Status:** Approved design (structure + visual layer), pre-implementation
**Repo:** `GUIs/rastering` (files: `raster_gui.ui`, `ui.py`)
**Wireframe options:** https://claude.ai/code/artifact/f7b3d105-fd50-4dc8-9042-50b9e111d4a1
**Hi-fi interactive mockup (approved):** https://claude.ai/code/artifact/ff7b9050-3de9-4663-b17b-696c0d50e89d

## Problem

The current two-tab layout (Automatic Controls / Manual Controls, 1280×720) is busy and
groups controls by mechanism rather than workflow:

1. "Delay (s)" (inter-point delay for continuous runs, `ui.py:1827`) is stranded in the
   window top bar, away from the raster controls it modifies.
2. Flip cam X/Y exist twice — top bar and Camera Settings dock — wired to the same state.
3. "Clear All Raster Points" exists on both tabs.
4. The Spiral group (6 spinboxes) is always visible even when the selected pattern is not
   spiral; there is no show/hide logic.
5. The Automatic/Manual split cuts across the daily workflow: arming/stepping is on one
   tab, jog on the other, so the operator switches tabs constantly, while rare
   calibration/backlash controls sit at equal visual weight beside daily jog buttons.
6. Status is buried: motor readouts are progress bars on the Manual tab; raster
   owner/shots-per-point are small labels inside a group box. Nothing survives a tab switch.

Operator-confirmed daily-use set: arm/step/stop for BLACS, manual jog/moves, camera tuning.
Must-see-at-a-glance set: raster owner, path progress, motor XY, camera + overlay.

## Design

### Window frame (outside the tab widget — always visible)

**Right side unchanged:** camera plot + path overlay on top, log box below, Camera
Settings dock (with View-menu toggle) on the right edge.

**Top bar removed.** Delay (s) moves to the Run tab; the two flip checkboxes are deleted
(the Camera Settings dock owns flip state — one control, same signals).

**Menu bar:** gains a **File** menu holding **"Save current as defaults"** (wired to the
existing `_on_save_defaults`) — it snapshots values across all tabs, so it belongs to the
window, not one tab's group box. The existing View menu (Camera Settings dock toggle,
Ctrl+Shift+C) is unchanged.

**Status strip** — permanent widgets in the existing `QStatusBar` (native Qt, no custom
widget class). Steady state shows six items; three warning chips appear only when their
condition is active (absence = all clear). Left to right:

| # | Item | Content / states | Source |
|---|------|------------------|--------|
| 1 | Owner/run badge | `IDLE` / `LOCAL RUN` / `ARMED · BLACS` (color-coded) | `_on_raster_source` + `_on_raster_state` |
| 2 | Path progress | `pt 37 / 220` | armed-path cursor (existing goto/selection state) |
| 3 | Shots per point | `×3/pt` (display-only; set in BLACS) | `_on_raster_shots_per_step` |
| 4 | Motor position | `X 4.213 · Y 1.008 mm` (numeric, `tabular` feel) | `_on_motor_position` |
| 5 | Calibration chip | `cal —` (none) / `cal 2/4` (collecting) / `cal ✓` (fresh) / `cal ✓ file` (loaded) / `cal stale` (camera geometry changed since cal) | `_on_calibration_progress`, `_on_calibration_ready`, `note_loaded_cal_bundle`; *stale* is a new comparison of current rotation/flip/AOI against the cal's bundled camera settings (`_get_cal_bundled_camera_settings`) — display-only, no new comms |
| 6 | Camera health | `cam 13.2 fps`; red / `cam —` when frames stop | existing `_fps_smoothed` metric (`set_frame`); staleness via a 2 s CoarseTimer watchdog |
| 7 | ⚠ `path edited — re-arm` | pattern changed since armed path was built | existing armed-vs-pending state (`_update_armed_pending_status`) |
| 8 | ⚠ `bounds OFF` | enforce-scan-bounds unchecked | `enforce_bounds_checkbox` state |
| 9 | ⚠ `● REC` | position-history CSV being written | `_pos_history_file is not None` |

### Tab 1 — Run (daily)

| Group | Contents | Origin |
|---|---|---|
| Raster | Auto Raster · Stop · Step · ☑ Continuous · Delay (s) · ☐ Save position history | Auto tab loose buttons + top-bar delay |
| Remote (BLACS) | Arm for remote stepping · Re-arm from pending · pt-index selector + Move to selected | programmatic Stepping/Remote group (`_install_raster_mode_controls`) |
| Move | dx/dy + jog ↑←→↓ · x/y + Move to Position + Preview Position · Go user home · Clear manual markers | Manual tab Jog + Move/Preview groups |

- "Go user home" = single button that goes to the stored user home (both axes). Defining
  home moves to Setup (split approved).
- "Clear manual markers" = renamed "Clear All Manual Points". The Run-tab duplicate of
  "Clear All Raster Points" is deleted; clearing raster points lives on Pattern only.

### Tab 2 — Pattern (occasional)

| Group | Contents | Origin |
|---|---|---|
| Pattern | algorithm combo · x step · y step · **spiral params group** (radius, step, angle, Δangle, cx, cy) shown **only when spiral selected** (`group_spiral.setVisible` driven by `alg_choice`) | Pattern + Step Size + Spiral groups |
| Scan bounds (px) | x low/high · y low/high · ☐ Enforce bounds | Scan Bounds group |
| Actions row | Preview Path · ☐ Show direction · Clear raster points · Save and Clear | Auto tab loose buttons |

### Tab 3 — Setup (rare)

| Group | Contents | Origin |
|---|---|---|
| Calibration | Calibrate (Affine) · Reset · Revert to Last · Save Calibration As… · Load Calibration… · Apply camera settings from cal · M·target+b matrix (6 spinboxes) | Manual tab calibration controls |
| Motor | Device Home X / Y / Both · Backlash x/y + Set · User home x/y setpoints + Set + per-axis Go | Device Home + Backlash + User Home groups. The combined-Go widget (`user_home_both`) IS Run's "Go user home" — one widget, no duplicate |
| Display | Show current position · Display points + count · Display raster points + count | Display Options group ("Save current as defaults" moves to the File menu) |

### Deleted outright

- Top-bar Flip cam X / Flip cam Y checkboxes (dock duplicates; `ui.py`'s legacy-checkbox
  fallback in `_install_camera_settings_dock` already handles their absence).
- One duplicate "Clear All Raster Points" button.
- Both motor progress bars (`progress_motor_x_pos/y_pos`) and the Readouts group —
  replaced by the numeric strip readout (approved). `_motor_to_percent` becomes dead code;
  remove it.

## Visual design (approved via hi-fi mockup)

Dark instrument-console treatment — camera-centric tool used in a dim lab. All of it is
plain Qt: Fusion style + dark `QPalette` + one QSS stylesheet built from six tokens.

**Palette tokens:**

| Token | Hex | Use |
|---|---|---|
| graphite | `#161A20` | window ground |
| panel | `#1E242C` | group boxes, dock |
| recess | `#12151A` | camera well, readout/input wells, status rail |
| ink / muted | `#D9E0E7` / `#8794A1` | text hierarchy |
| steel cyan | `#3EB4C8` | interactive emphasis + armed state ONLY |
| signal amber / confirm green / alert red | `#E2A83D` / `#52BE6E` / `#E15A4D` | annunciator semantics — never decoration |

**Type:** app default Segoe UI for controls; `QGroupBox::title` uppercase +
letter-spaced + muted via QSS; every numeric readout (spinboxes, strip labels) gets
Cascadia Code (fallback Consolas) for tabular instrument-style digits.

**Status strip = annunciator rail:** chips are QLabels added with
`QStatusBar.addPermanentWidget`, styled via a dynamic property
(`chip.setProperty("state", "amber")` + QSS `QLabel[state="amber"]`, with
`style().unpolish/polish` on change). Each chip has a small square "lamp"; warning chips
toggle `setVisible` — unlit/absent means all clear. Optional 1 Hz REC blink via a
CoarseTimer QTimer (never PreciseTimer on the GUI thread).

**Buttons:** primary actions (Auto Raster, Stop, Arm, Preview Path, Calibrate) get the
cyan-outline primary style; armed state fills cyan-tinted. 3 px radii, no gradients
beyond a subtle vertical button face.

## Implementation shape

- **`raster_gui.ui`:** three tabs instead of two; groups moved per the tables; top-bar row
  removed; spiral params inside a `QStackedWidget`. This is the bulk of the change.
- **`ui.py`:** contained edits —
  - `_install_raster_mode_controls` retargets its widgets into the Run-tab layout
    (rename the layout anchor from `autoLayout` accordingly; keep the no-anchor fallback).
  - New `_install_status_strip` builds the 9 strip widgets once in `__init__` and
    subscribes to the existing signals listed above. Conditional chips toggle visibility,
    never re-create widgets.
  - Spiral visibility: connect `alg_choice.currentIndexChanged` → `group_spiral.setVisible`.
  - `cal stale` check + fps counter as described (both display-only).
  - Delete `_motor_to_percent` and progress-bar update code in `_on_motor_position`.
  - File menu action "Save current as defaults" → existing `_on_save_defaults`
    (button removed from the Display group).
  - Apply the visual layer: Fusion + dark QPalette + the token QSS stylesheet
    (single module-level constant or `.qss` file), mono font on numeric widgets.
- **No controller changes.** No signal/slot semantics change, no ZMQ change, no new
  communication flows. Layout + display only.
- Widget object names are preserved wherever the widget survives, so
  `_connect_ui_actions` wiring and saved user defaults (`_gather_user_defaults` /
  `_apply_user_defaults`) keep working; any name that must change gets a migration note
  in the implementation plan.

## Error handling

- Strip updates are passive consumers of existing signals; a missing/none value renders
  as `—`, never raises (a raise in a slot would yellow the operator GUI).
- `cal stale` comparison is defensive: if the loaded cal has no bundled camera settings,
  the state stays `cal ✓ file` (unknown ≠ stale).
- fps counter: timer-based decay so a stalled feed reads `cam —` rather than freezing the
  last value.

## Testing

- Camera-safe suites must stay green: `pytest tests/test_raster_pathmodel.py
  tests/test_zmq_v2_protocol.py` (never run ui-importing tests while the GUI/camera runs).
- Extend the existing UI-level test pattern (`tests/test_ui_slowdown_guards.py`) with
  strip-state assertions where feasible (widget-existence + state transitions under
  simulated signals), run only when the camera is free.
- Manual verification in sim mode: `RASTER_SIMULATE=1 python main_rastering.py` — check
  every moved control fires (jog, arm, step, preview, calibrate entry), spiral panel
  appears only for spiral, strip states cycle correctly.
- `python -m py_compile ui.py` for quick syntax checks while the camera is busy.

## Out of scope

- Camera Settings dock internals (unchanged).
- Any controller (`raster_controller.py`) behavior.
- BLACS-side RasteringDevice.

## Rollout

Dev on a topic-branch worktree (live `GUIs/rastering` runs `main` between shots — never
park half-applied work there). Deploy = operator restarts the GUI. One-time muscle-memory
reset accepted by operator (2026-08-11 conversation).
