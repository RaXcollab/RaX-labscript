# Rastering GUI UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the rastering GUI into Run / Pattern / Setup tabs with an always-visible annunciator status strip and a dark instrument-console theme, per the approved spec `docs/superpowers/specs/2026-08-12-rastering-ui-redesign-design.md`.

**Architecture:** Layout-only change. `raster_gui.ui` is restructured (3 tabs, deduplicated controls); two new small modules (`status_strip.py` for chip logic, `theme.py` for QSS/palette) keep testable units out of the 2500-line `ui.py`; `ui.py` gets contained edits (strip wiring, deletions, File menu). **No controller (`raster_controller.py`) changes, no ZMQ changes, no new communication flows.**

**Tech Stack:** PyQt5 (uic-loaded `.ui`), pytest, conda env `rastering`.

## Global Constraints

- **Repo:** `GUIs/rastering` is its own git repo (`RaXcollab/rastering`), separate from the parent. All commits in this plan go to THAT repo, on the topic branch in the worktree (Task 1). NEVER commit to the live checkout `GUIs/rastering` (operator runs `main` between shots).
- **Conda env:** every Python/pytest command: `source ~/miniconda/etc/profile.d/conda.sh && conda activate rastering` (env `rastering`, NOT `labscript`).
- **Camera-safe tests** (safe to run anytime, must be green before every commit): `python -m pytest tests/test_raster_pathmodel.py tests/test_zmq_v2_protocol.py tests/test_raster_gui_ui_structure.py tests/test_status_strip.py -q` (the last two are created by this plan; drop them from the command until they exist).
- **Camera-CAVEAT tests** (import `ui.py` → touch pyueye): `tests/test_ui_slowdown_guards.py`, `tests/test_ui_redesign_wiring.py` (new), `test_command_queue.py`, `test_raster_goto_handlers.py`. NEVER run while the rastering GUI (or anything holding the uEye camera) is running. If they skip with an import error, report it — do not silently pass.
- **Syntax check while camera busy:** `python -m py_compile ui.py status_strip.py theme.py`.
- **`.ui` validity check (no camera, no display):** `python -c "from PyQt5 import uic; uic.loadUiType('raster_gui.ui'); print('ui OK')"`.
- **Every commit leaves the app startable:** paired `.ui` + `ui.py` changes (a widget deletion and the code that referenced it) land in the SAME commit.
- **Widget object names are preserved** for every surviving widget (`start_button`, `xstep`, `alg_choice`, `checkBox_2`, ...) so `_connect_ui_actions` and `settings_defaults` keep working. Only containers/tabs are new.
- **No `pyqtgraph`/plot changes**; camera dock (`camera_settings_dock.py`) unchanged.
- Windows: use the Bash tool with POSIX syntax for git/pytest; `RASTER_SIMULATE=1 python main_rastering.py` for sim smoke runs.

---

### Task 1: Topic-branch worktree + green baseline

**Files:** none modified (setup only).

**Interfaces:**
- Produces: worktree at `GUIs/rastering-ui-redesign` on branch `feat/ui-redesign`; all subsequent tasks run inside it.

- [ ] **Step 1: Create the worktree** (from the live checkout — read-only for it)

```bash
cd "/c/Users/radmo/labscript-suite/GUIs/rastering"
git worktree add ../rastering-ui-redesign -b feat/ui-redesign
```

- [ ] **Step 2: Baseline camera-safe tests**

```bash
cd "/c/Users/radmo/labscript-suite/GUIs/rastering-ui-redesign"
source ~/miniconda/etc/profile.d/conda.sh && conda activate rastering
python -m pytest tests/test_raster_pathmodel.py tests/test_zmq_v2_protocol.py -q
```
Expected: all pass. If not, STOP and report — the baseline is broken, not this plan.

- [ ] **Step 3: Record baseline** — note the HEAD hash (`git rev-parse --short HEAD`) in the task report. No commit.

---

### Task 2: `.ui` restructure — three tabs, groups moved (no deletions yet)

**Files:**
- Test: `tests/test_raster_gui_ui_structure.py` (create)
- Modify: `raster_gui.ui`
- Modify: `ui.py` (one line: remote-group insert index)

**Interfaces:**
- Consumes: current `raster_gui.ui` tree — `tab` ("Automatic Controls", layout `autoLayout` containing `autoButtonsLayout`, `autoModeLayout`, `group_steps`, `group_pattern`, `group_bounds`, `group_spiral`, loose buttons) and `tab_2` ("Manual Controls", layout `manualLayout` containing `manualTopButtons`, `calFileButtons`, `group_calmat`, `group_move`, `group_readouts`, `group_jog`, `group_device_home`, `group_user_home`, `group_backlash`, `group_display_options`).
- Produces: `tab` retitled **"Run"**, new `tab_pattern` titled **"Pattern"** (layout `patternTabLayout`), `tab_2` retitled **"Setup"**. New `group_raster` QGroupBox on Run. Tab order: Run, Pattern, Setup. Every widget object name unchanged.

Target tree after this task (deletions happen in Task 3):

```
tab "Run" (autoLayout):
  group_raster "Raster" (NEW QGroupBox, QGridLayout grid_raster):
    row0: start_button | stop_button | raster_step_button
    row1: raster_continuous_checkbox | label_timer | sleepTimer   <- moved from horizontalLayout_Top
    row2: checkBox_2 ("Save position history")
  group_jog  (moved from tab_2, still contains clearAllRasterManual until Task 3)
  group_move (moved from tab_2)
  vertical spacer
tab_pattern "Pattern" (patternTabLayout QVBoxLayout, NEW):
  group_pattern
  group_steps
  group_spiral
  group_bounds
  patternActionsLayout (NEW QHBoxLayout): path_button | clearAll | save_button
  vertical spacer
tab_2 "Setup" (manualLayout):
  manualTopButtons, calFileButtons, group_calmat,
  group_readouts (deleted in Task 3), group_device_home,
  group_user_home, group_backlash, group_display_options, spacer
top bar horizontalLayout_Top: still present but now holds only line_v3 + flip checkboxes
  (label_timer + sleepTimer moved out; row fully deleted in Task 3)
```

- [ ] **Step 1: Write the failing structure test.** Create `tests/test_raster_gui_ui_structure.py` — pure XML, zero Qt imports, camera-safe:

```python
"""Structural assertions on raster_gui.ui (pure XML — camera-safe, no Qt).

Encodes the 2026-08-12 redesign: Run / Pattern / Setup tabs, deduplicated
controls, always-on status strip (strip itself is code, not .ui).
Standalone-runnable: conda activate rastering && python -m pytest tests/test_raster_gui_ui_structure.py
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

UI_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "raster_gui.ui")


def _root():
    return ET.parse(UI_PATH).getroot()


def _tab_widget(root):
    for w in root.iter("widget"):
        if w.get("class") == "QTabWidget":
            return w
    raise AssertionError("no QTabWidget in raster_gui.ui")


def _tab_titles(root):
    titles = []
    for tab in _tab_widget(root).findall("widget"):
        for attr in tab.findall("attribute"):
            if attr.get("name") == "title":
                titles.append(attr.find("string").text)
    return titles


def _names_under(el):
    return {w.get("name") for w in el.iter("widget")}


def _tab_by_title(root, title):
    for tab in _tab_widget(root).findall("widget"):
        for attr in tab.findall("attribute"):
            if attr.get("name") == "title" and attr.find("string").text == title:
                return tab
    raise AssertionError(f"no tab titled {title!r}")


def test_three_tabs_in_order():
    assert _tab_titles(_root()) == ["Run", "Pattern", "Setup"]


def test_run_tab_contents():
    names = _names_under(_tab_by_title(_root(), "Run"))
    for expected in ("group_raster", "start_button", "stop_button",
                     "raster_step_button", "raster_continuous_checkbox",
                     "sleepTimer", "checkBox_2", "group_jog", "group_move"):
        assert expected in names, f"{expected} missing from Run tab"


def test_pattern_tab_contents():
    names = _names_under(_tab_by_title(_root(), "Pattern"))
    for expected in ("group_pattern", "alg_choice", "group_steps", "xstep",
                     "ystep", "group_spiral", "group_bounds",
                     "enforce_bounds_checkbox", "path_button", "clearAll",
                     "save_button"):
        assert expected in names, f"{expected} missing from Pattern tab"


def test_setup_tab_contents():
    names = _names_under(_tab_by_title(_root(), "Setup"))
    for expected in ("calibrateButton", "group_calmat", "group_device_home",
                     "group_user_home", "group_backlash",
                     "group_display_options"):
        assert expected in names, f"{expected} missing from Setup tab"


def test_no_widget_name_lost_or_duplicated():
    # Every object name in the file must be unique (uic requires it).
    names = [w.get("name") for w in _root().iter("widget") if w.get("name")]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate object names: {dupes}"
```

- [ ] **Step 2: Run it — must fail on the current file**

```bash
python -m pytest tests/test_raster_gui_ui_structure.py -q
```
Expected: FAIL on `test_three_tabs_in_order` (titles are still "Automatic Controls"/"Manual Controls").

- [ ] **Step 3: Restructure `raster_gui.ui`.** Edit the XML directly (whole `<item><widget>...</widget></item>` subtrees move verbatim — cut/paste, do not retype widget internals):
  1. Retitle `tab` → `Run`, `tab_2` → `Setup` (the `<attribute name="title"><string>` under each tab).
  2. Insert new `tab_pattern` between them:
     ```xml
     <widget class="QWidget" name="tab_pattern">
      <attribute name="title"><string>Pattern</string></attribute>
      <layout class="QVBoxLayout" name="patternTabLayout">
       <!-- items moved here in the next steps -->
      </layout>
     </widget>
     ```
  3. Create `group_raster` as the first item of `autoLayout`:
     ```xml
     <item>
      <widget class="QGroupBox" name="group_raster">
       <property name="title"><string>Raster</string></property>
       <layout class="QGridLayout" name="grid_raster">
        <!-- row0: start_button, stop_button, raster_step_button (moved from autoButtonsLayout/autoModeLayout) -->
        <!-- row1: raster_continuous_checkbox, label_timer, sleepTimer -->
        <!-- row2: checkBox_2 -->
       </layout>
      </widget>
     </item>
     ```
     Move `start_button`, `stop_button` out of `autoButtonsLayout`; `raster_continuous_checkbox`, `raster_step_button` out of `autoModeLayout`; `label_timer` + `sleepTimer` out of `horizontalLayout_Top`; `checkBox_2` from `autoLayout`. Delete the now-empty `autoButtonsLayout`/`autoModeLayout`.
  4. Move `group_pattern`, `group_steps`, `group_spiral`, `group_bounds` subtrees from `autoLayout` into `patternTabLayout`; move `path_button`, `clearAll`, `save_button` into a new `patternActionsLayout` QHBoxLayout at the bottom of `patternTabLayout`; end with a vertical spacer.
  5. Move `group_jog` and `group_move` subtrees from `manualLayout` into `autoLayout` (after `group_raster`); end `autoLayout` with a vertical spacer.
- [ ] **Step 4: Adjust the remote-group insert index in `ui.py`.** In `_install_raster_mode_controls`, change `_auto_layout.insertWidget(2, self.raster_remote_group)` to `_auto_layout.insertWidget(1, self.raster_remote_group)` and update the comment (index 1 = right under the Raster group).
- [ ] **Step 5: Validate**

```bash
python -m pytest tests/test_raster_gui_ui_structure.py -q
python -c "from PyQt5 import uic; uic.loadUiType('raster_gui.ui'); print('ui OK')"
python -m py_compile ui.py
```
Expected: tests PASS, `ui OK`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_raster_gui_ui_structure.py raster_gui.ui ui.py
git commit -m "refactor(ui): re-cut tabs by frequency — Run / Pattern / Setup

Structure-only .ui move: no widget renamed, no control deleted yet.
XML structure tests added (camera-safe, pure ElementTree)."
```

---

### Task 3: Deduplicate + rehome (paired `.ui` + `ui.py` deletions, File menu)

**Files:**
- Modify: `raster_gui.ui`
- Modify: `ui.py` (`_connect_ui_actions`, `_on_motor_position`, delete `_motor_to_percent`, new `_install_file_menu`)
- Test: `tests/test_raster_gui_ui_structure.py` (extend)

**Interfaces:**
- Consumes: Task 2 tree.
- Produces: deletions listed below; `self.save_defaults_action` (QAction, replaces `save_defaults_button`); `user_home_both` lives in `group_move` with text "Go user home". `_on_motor_position(mx, my)` body reduced to a strip update placeholder call `self._update_strip_motor(mx, my)` — defined here as a no-op logging-free stub, replaced by the real strip call in Task 5 (keeps this commit runnable).

Deletions (each `.ui` removal paired with its `ui.py` reference in THIS commit):

| Deleted from `.ui` | `ui.py` change |
|---|---|
| `flip_x_checkbox`, `flip_y_checkbox`, `line_v3`, the whole `horizontalLayout_Top` row | none needed — `_install_camera_settings_dock` already aliases `self.flip_x_checkbox = self.cam_dock.flip_x_cb` when absent |
| `clearAllRasterManual` (duplicate "Clear All Raster Points" in `group_jog`) | remove `self.clearAllRasterManual.clicked.connect(self._clear_raster_points)` from `_connect_ui_actions` |
| `group_readouts` + `progress_motor_x_pos` + `progress_motor_y_pos` | delete `_motor_to_percent` entirely; in `_on_motor_position` delete the two `hasattr(self, "progress_motor_*")` blocks AND the dead `motor_x_pos`/`motor_y_pos` label blocks; body becomes `self._update_strip_motor(mx, my)` (stub this task: `def _update_strip_motor(self, mx, my): pass  # replaced by status strip in Task 5`) |
| `save_defaults_button` (from `group_display_options`) | remove `self.save_defaults_button.clicked.connect(self._on_save_defaults)`; add `_install_file_menu` (below), called in `__init__` immediately BEFORE `self._install_camera_settings_dock()` so File sits left of View |

- [ ] **Step 1: Extend the structure test** — append to `tests/test_raster_gui_ui_structure.py`:

```python
def test_deleted_widgets_stay_deleted():
    names = _names_under(_root())
    for gone in ("flip_x_checkbox", "flip_y_checkbox", "clearAllRasterManual",
                 "group_readouts", "progress_motor_x_pos",
                 "progress_motor_y_pos", "save_defaults_button"):
        assert gone not in names, f"{gone} should have been deleted"


def test_user_home_both_lives_in_move_group_as_go_user_home():
    root = _root()
    move_names = _names_under(_tab_by_title(root, "Run"))
    assert "user_home_both" in move_names
    for w in root.iter("widget"):
        if w.get("name") == "user_home_both":
            for prop in w.findall("property"):
                if prop.get("name") == "text":
                    assert prop.find("string").text == "Go user home"
                    return
    raise AssertionError("user_home_both text property not found")
```

- [ ] **Step 2: Run — both new tests must FAIL** (`python -m pytest tests/test_raster_gui_ui_structure.py -q`).
- [ ] **Step 3: Apply the `.ui` deletions** per the table; move the `user_home_both` widget subtree from `grid_user_home` into `grid_move` (bottom row) and change its `text` property to `Go user home`. Relabel `clearAllManual`'s text to `Clear manual markers`. Retitle groups to final copy: `group_jog` → `Jog (mm)`, `group_move` → `Move (mm)`, `group_bounds` → `Scan bounds (image px)`, `group_spiral` → `Spiral parameters (px / rad)`.
- [ ] **Step 4: Apply the `ui.py` changes** per the table, plus:

```python
def _install_file_menu(self) -> None:
    """File menu: window-scoped actions. 'Save current as defaults'
    snapshots values across all tabs, so it belongs to the window,
    not one tab's group box (2026-08-12 redesign)."""
    m = self.menuBar().addMenu("&File")
    self.save_defaults_action = m.addAction("Save current as defaults")
    self.save_defaults_action.setShortcut(QtGui.QKeySequence("Ctrl+D"))
    self.save_defaults_action.triggered.connect(self._on_save_defaults)
```

In `__init__`, directly above `self._install_camera_settings_dock()`:

```python
        # --- File menu (before the dock installs the View menu) ---
        self._install_file_menu()
```

- [ ] **Step 5: Validate**

```bash
python -m pytest tests/test_raster_gui_ui_structure.py -q
python -c "from PyQt5 import uic; uic.loadUiType('raster_gui.ui'); print('ui OK')"
python -m py_compile ui.py
```

- [ ] **Step 6: Commit**

```bash
git add raster_gui.ui ui.py tests/test_raster_gui_ui_structure.py
git commit -m "refactor(ui): dedupe controls, File-menu save-defaults, drop progress bars

Deleted: top-bar flip duplicates + delay row home, duplicate clear-raster
button, Readouts progress bars (+_motor_to_percent). 'Save current as
defaults' -> File menu (Ctrl+D). user_home_both -> Move group as 'Go
user home'."
```

---

### Task 4: Spiral params visible only for spiral patterns

**Files:**
- Modify: `ui.py`
- Test: `tests/test_ui_redesign_wiring.py` (create)

**Interfaces:**
- Consumes: `group_spiral` on the Pattern tab (Task 2); `alg_choice` items are `Square Raster X`, `Square Raster Y`, `Spiral Raster`, `Convex Hull Raster`; `_build_raster_spec` picks spiral via `"spiral" in alg_text.lower()` — reuse the same rule.
- Produces: `RasterMainWindow._update_spiral_visibility()` — sets `self.group_spiral.setVisible("spiral" in self.alg_choice.currentText().lower())`.

Note: the spec named a `QStackedWidget`; plain `setVisible` on the existing group achieves the identical visible-only-when-spiral behavior with no new container and no reserved blank space — deliberate simplification.

- [ ] **Step 1: Write the failing test.** Create `tests/test_ui_redesign_wiring.py`:

```python
"""Duck-typed wiring tests for the 2026-08-12 UI redesign glue in ui.py.

CAMERA CAVEAT (same as test_ui_slowdown_guards.py): importing ui.py pulls
in PyQt5 + pyueye. Never run while the rastering GUI is running.
Standalone-runnable:
    conda activate rastering && python -m pytest tests/test_ui_redesign_wiring.py
"""
from __future__ import annotations

import os
import sys
import types
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import ui  # noqa: E402
    _UI_IMPORT_ERROR = None
except Exception as e:  # noqa: BLE001
    ui = None
    _UI_IMPORT_ERROR = e


def _require_ui():
    if ui is None:
        import pytest
        pytest.skip(f"ui.py not importable here: {_UI_IMPORT_ERROR}")


def _spiral_self(text):
    return types.SimpleNamespace(
        alg_choice=types.SimpleNamespace(currentText=lambda: text),
        group_spiral=mock.Mock(name="group_spiral"),
    )


def test_spiral_group_shown_for_spiral():
    _require_ui()
    fake = _spiral_self("Spiral Raster")
    ui.RasterMainWindow._update_spiral_visibility(fake)
    fake.group_spiral.setVisible.assert_called_once_with(True)


def test_spiral_group_hidden_for_square():
    _require_ui()
    fake = _spiral_self("Square Raster X")
    ui.RasterMainWindow._update_spiral_visibility(fake)
    fake.group_spiral.setVisible.assert_called_once_with(False)
```

- [ ] **Step 2: Run — FAIL** with `AttributeError: ... no attribute '_update_spiral_visibility'` (`python -m pytest tests/test_ui_redesign_wiring.py -q`; skip cleanly means the camera is busy — wait, don't force).
- [ ] **Step 3: Implement.** In `ui.py` next to `_on_raster_param_changed`:

```python
    def _update_spiral_visibility(self) -> None:
        """Spiral parameters only exist on screen while a spiral pattern is
        selected -- same text rule _build_raster_spec uses."""
        self.group_spiral.setVisible("spiral" in self.alg_choice.currentText().lower())
```

In `_connect_ui_actions`, right after the existing `self.alg_choice.currentIndexChanged.connect(self._on_raster_param_changed)`:

```python
        self.alg_choice.currentIndexChanged.connect(self._update_spiral_visibility)
```

In `__init__`, right after `self._connect_ui_actions()`:

```python
        self._update_spiral_visibility()  # initial: hidden unless spiral selected
```

- [ ] **Step 4: Run — PASS** (`python -m pytest tests/test_ui_redesign_wiring.py -q`), plus `python -m py_compile ui.py`.
- [ ] **Step 5: Commit**

```bash
git add ui.py tests/test_ui_redesign_wiring.py
git commit -m "feat(ui): spiral parameter group visible only for spiral patterns"
```

---

### Task 5: `status_strip.py` — pure chip logic + StatusStrip widget (TDD)

**Files:**
- Create: `status_strip.py`
- Test: `tests/test_status_strip.py` (create)

**Interfaces:**
- Consumes: nothing from `ui.py` (module must NOT import `ui`, `camera`, or `pyueye` — that keeps its tests camera-safe).
- Produces (exact signatures — Task 6 and `theme.py` rely on them):
  - `owner_state(active: bool, source) -> tuple[str, str]` — `("IDLE","idle") | ("LOCAL RUN","good") | ("ARMED · BLACS","cyan")`
  - `progress_text(index: int, total: int) -> str` — `"pt — / —"` when `total <= 0`, else `"pt {index} / {total}"`
  - `shots_text(n) -> str` — `"— /pt"` when `n is None`, else `"×{n} /pt"`
  - `motor_text(mx, my) -> str` — `"X — · Y — mm"` when either is None, else `"X {mx:.3f} · Y {my:.3f} mm"`
  - `cal_state(has_cal: bool, collecting, from_file: bool, stale: bool) -> tuple[str, str]` — collecting=(got, need) → `("cal {got}/{need}","warn")`; no cal → `("cal —","idle")`; stale → `("cal stale","warn")`; else `("cal ✓ file","good")` / `("cal ✓","good")`
  - `fps_text(fps, stalled: bool) -> tuple[str, str]` — stalled or None → `("cam —","warn")`, else `("cam {fps:.1f} fps","idle")`
  - `geometry_stale(current, bundled) -> bool` — recursive intersection compare; missing dicts/keys are never stale
  - `class StatusStrip(statusbar)` with `.set_chip(key, text, state="idle")` (no-op when text+state unchanged) and `.set_warning(key, on: bool)`; chip keys `owner, progress, shots, motor, cal, fps` (always visible) and `pending, bounds, rec` (hidden until `set_warning(key, True)`); every chip is a `QLabel` with `objectName "chip_<key>"` and dynamic property `chipState` ∈ `idle|good|cyan|warn|alert`, repolished on change.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_status_strip.py`:

```python
"""status_strip pure-logic + widget tests. Camera-safe: status_strip
imports PyQt5 only (no ui.py, no pyueye). Widget tests run offscreen.
Standalone-runnable:
    conda activate rastering && python -m pytest tests/test_status_strip.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import status_strip as ss  # noqa: E402


def test_owner_state():
    assert ss.owner_state(False, None) == ("IDLE", "idle")
    assert ss.owner_state(True, "local") == ("LOCAL RUN", "good")
    assert ss.owner_state(True, "remote") == ("ARMED · BLACS", "cyan")
    assert ss.owner_state(False, "remote") == ("IDLE", "idle")  # stale source, inactive


def test_progress_text():
    assert ss.progress_text(0, 0) == "pt — / —"
    assert ss.progress_text(37, 150) == "pt 37 / 150"


def test_shots_text():
    assert ss.shots_text(None) == "— /pt"
    assert ss.shots_text(3) == "×3 /pt"


def test_motor_text():
    assert ss.motor_text(None, None) == "X — · Y — mm"
    assert ss.motor_text(4.2134, 1.0) == "X 4.213 · Y 1.000 mm"


def test_cal_state_priority():
    assert ss.cal_state(False, None, False, False) == ("cal —", "idle")
    assert ss.cal_state(False, (2, 4), False, False) == ("cal 2/4", "warn")
    assert ss.cal_state(True, None, False, False) == ("cal ✓", "good")
    assert ss.cal_state(True, None, True, False) == ("cal ✓ file", "good")
    assert ss.cal_state(True, None, True, True) == ("cal stale", "warn")


def test_fps_text():
    assert ss.fps_text(13.24, False) == ("cam 13.2 fps", "idle")
    assert ss.fps_text(13.2, True) == ("cam —", "warn")
    assert ss.fps_text(None, False) == ("cam —", "warn")


def test_geometry_stale_intersection_only():
    bundled = {"rotation_k": -1, "flip_x": False,
               "aoi": {"width": 656, "height": 440}}
    same = {"rotation_k": -1, "flip_x": False, "flip_y": True,  # extra key ignored
            "aoi": {"width": 656, "height": 440, "start_x": 0}}
    assert ss.geometry_stale(same, bundled) is False
    rotated = dict(same, rotation_k=2)
    assert ss.geometry_stale(rotated, bundled) is True
    aoi_changed = dict(same, aoi={"width": 328, "height": 440})
    assert ss.geometry_stale(aoi_changed, bundled) is True
    assert ss.geometry_stale(None, bundled) is False   # unknown != stale
    assert ss.geometry_stale(same, None) is False


def _strip():
    from PyQt5 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bar = QtWidgets.QStatusBar()
    return app, bar, ss.StatusStrip(bar)


def test_warning_chips_start_hidden_and_toggle():
    _app, _bar, strip = _strip()
    for key in ("pending", "bounds", "rec"):
        assert not strip._chips[key].isVisibleTo(_bar)
    strip.set_warning("rec", True)
    assert strip._chips["rec"].isVisibleTo(_bar)
    strip.set_warning("rec", False)
    assert not strip._chips["rec"].isVisibleTo(_bar)


def test_set_chip_updates_text_and_state_property():
    _app, _bar, strip = _strip()
    strip.set_chip("owner", "ARMED · BLACS", "cyan")
    lab = strip._chips["owner"]
    assert lab.text() == "ARMED · BLACS"
    assert lab.property("chipState") == "cyan"
```

- [ ] **Step 2: Run — FAIL** with `ModuleNotFoundError: status_strip` (`python -m pytest tests/test_status_strip.py -q`).
- [ ] **Step 3: Implement `status_strip.py`:**

```python
"""Annunciator status strip for the rastering GUI (2026-08-12 redesign).

Pure chip-state functions first (unit-testable, no Qt needed), then the
StatusStrip widget wrapper. This module must never import ui, camera, or
pyueye -- its tests are camera-safe BECAUSE of that.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from PyQt5 import QtWidgets

ALWAYS_CHIPS = ("owner", "progress", "shots", "motor", "cal", "fps")
WARNING_CHIPS = ("pending", "bounds", "rec")
_WARNING_TEXT = {"pending": "PATH EDITED — RE-ARM", "bounds": "BOUNDS OFF", "rec": "● REC"}
_WARNING_STATE = {"pending": "warn", "bounds": "warn", "rec": "alert"}


def owner_state(active: bool, source) -> Tuple[str, str]:
    if active and source == "remote":
        return ("ARMED · BLACS", "cyan")
    if active:
        return ("LOCAL RUN", "good")
    return ("IDLE", "idle")


def progress_text(index: int, total: int) -> str:
    if total <= 0:
        return "pt — / —"
    return f"pt {index} / {total}"


def shots_text(n) -> str:
    return "— /pt" if n is None else f"×{int(n)} /pt"


def motor_text(mx, my) -> str:
    if mx is None or my is None:
        return "X — · Y — mm"
    return f"X {mx:.3f} · Y {my:.3f} mm"


def cal_state(has_cal: bool, collecting, from_file: bool, stale: bool) -> Tuple[str, str]:
    if collecting is not None:
        return (f"cal {int(collecting[0])}/{int(collecting[1])}", "warn")
    if not has_cal:
        return ("cal —", "idle")
    if stale:
        return ("cal stale", "warn")
    return ("cal ✓ file", "good") if from_file else ("cal ✓", "good")


def fps_text(fps, stalled: bool) -> Tuple[str, str]:
    if stalled or fps is None:
        return ("cam —", "warn")
    return (f"cam {fps:.1f} fps", "idle")


def geometry_stale(current: Optional[Dict[str, Any]],
                   bundled: Optional[Dict[str, Any]]) -> bool:
    """True when any key present in BOTH dicts disagrees (recursing into
    nested dicts, e.g. 'aoi'). Missing data is never stale -- an old
    calibration file without bundled settings must read 'cal ✓ file',
    not 'cal stale'."""
    if not current or not bundled:
        return False
    for key, b_val in bundled.items():
        if key not in current:
            continue
        c_val = current[key]
        if isinstance(b_val, dict) and isinstance(c_val, dict):
            if geometry_stale(c_val, b_val):
                return True
        elif c_val != b_val:
            return True
    return False


class StatusStrip:
    """Chips in an existing QStatusBar. Display-only: a consumer of state,
    never a raiser -- a raise in a status slot would yellow the operator
    GUI, so setters are guarded and idempotent."""

    def __init__(self, statusbar: QtWidgets.QStatusBar) -> None:
        self._chips: Dict[str, QtWidgets.QLabel] = {}
        for key in ALWAYS_CHIPS + WARNING_CHIPS:
            lab = QtWidgets.QLabel()
            lab.setObjectName(f"chip_{key}")
            lab.setProperty("chipState", "idle")
            statusbar.addPermanentWidget(lab)
            self._chips[key] = lab
        for key in WARNING_CHIPS:
            self._chips[key].setText(_WARNING_TEXT[key])
            self._set_state(self._chips[key], _WARNING_STATE[key])
            self._chips[key].setVisible(False)

    @staticmethod
    def _set_state(lab: QtWidgets.QLabel, state: str) -> None:
        if lab.property("chipState") != state:
            lab.setProperty("chipState", state)
            lab.style().unpolish(lab)
            lab.style().polish(lab)

    def set_chip(self, key: str, text: str, state: str = "idle") -> None:
        lab = self._chips[key]
        if lab.text() != text:          # ~4 Hz telemetry feeds this; skip
            lab.setText(text)           # no-op repaints
        self._set_state(lab, state)

    def set_warning(self, key: str, on: bool) -> None:
        self._chips[key].setVisible(bool(on))
```

- [ ] **Step 4: Run — PASS** (`python -m pytest tests/test_status_strip.py -q`).
- [ ] **Step 5: Commit**

```bash
git add status_strip.py tests/test_status_strip.py
git commit -m "feat: status_strip module — annunciator chip logic + widget (camera-safe tests)"
```

---

### Task 6: Wire the strip into `ui.py`

**Files:**
- Modify: `ui.py`
- Test: `tests/test_ui_redesign_wiring.py` (extend)

**Interfaces:**
- Consumes: everything Task 5 produces; existing controller signals (`raster_state_signal`, `raster_source_signal`, `raster_shots_per_step_signal`, `motor_position_signal`, `target_position_signal`, calibration signals); existing state `self._raster_active_ui`, `self._last_raster_source`, `self._raster_preview_pts`, `self._pos_history_file`, `self._fps_smoothed`, `self._last_frame_time`, `self.controller._raster_index` / `_raster_total_steps` (private reads — precedent: `_on_raster_state` already reads `_raster_total_steps`), `self.controller.armed_path_points()`, `self._get_cal_bundled_camera_settings()`, `self._loaded_cal_bundle_camera_settings`.
- Produces: `self.status_strip` (StatusStrip); methods `_update_strip_owner`, `_update_strip_progress`, `_update_strip_motor` (replaces Task 3 stub), `_update_strip_cal`, `_update_strip_pending`, `_update_strip_slow`, `_strip_refresh_all`; cal-tracking attrs `_cal_collecting`, `_cal_from_file`, `_cal_geometry_at_ready`. The old `raster_source_label` / `raster_shots_label` are REMOVED from `_install_raster_mode_controls` (the strip owns both readouts now).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_ui_redesign_wiring.py`:

```python
def _strip_self(**over):
    base = dict(
        status_strip=mock.Mock(name="status_strip"),
        controller=types.SimpleNamespace(
            _raster_index=37, _raster_total_steps=150, calibration=object(),
            armed_path_points=lambda: [0] * 150),
        _raster_active_ui=True,
        _last_raster_source="remote",
        _raster_preview_pts=[],
        _cal_collecting=None,
        _cal_from_file=False,
        _cal_geometry_at_ready=None,
        _loaded_cal_bundle_camera_settings=None,
        _get_cal_bundled_camera_settings=lambda: None,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def test_strip_owner_armed_blacs():
    _require_ui()
    fake = _strip_self()
    ui.RasterMainWindow._update_strip_owner(fake)
    fake.status_strip.set_chip.assert_called_once_with("owner", "ARMED · BLACS", "cyan")


def test_strip_progress_active_vs_idle():
    _require_ui()
    fake = _strip_self()
    ui.RasterMainWindow._update_strip_progress(fake)
    fake.status_strip.set_chip.assert_called_once_with("progress", "pt 37 / 150")
    idle = _strip_self(_raster_active_ui=False)
    ui.RasterMainWindow._update_strip_progress(idle)
    idle.status_strip.set_chip.assert_called_once_with("progress", "pt — / —")


def test_strip_motor_chip():
    _require_ui()
    fake = _strip_self()
    ui.RasterMainWindow._update_strip_motor(fake, 4.2134, 1.0)
    fake.status_strip.set_chip.assert_called_once_with("motor", "X 4.213 · Y 1.000 mm")


def test_strip_pending_lights_only_on_count_mismatch():
    _require_ui()
    fake = _strip_self(_raster_preview_pts=[0] * 149)
    ui.RasterMainWindow._update_strip_pending(fake)
    fake.status_strip.set_warning.assert_called_once_with("pending", True)
    matched = _strip_self(_raster_preview_pts=[0] * 150)
    ui.RasterMainWindow._update_strip_pending(matched)
    matched.status_strip.set_warning.assert_called_once_with("pending", False)


def test_strip_cal_stale_when_geometry_diverged():
    _require_ui()
    fake = _strip_self(
        _cal_from_file=True,
        _loaded_cal_bundle_camera_settings={"rotation_k": -1},
        _get_cal_bundled_camera_settings=lambda: {"rotation_k": 2},
    )
    ui.RasterMainWindow._update_strip_cal(fake)
    fake.status_strip.set_chip.assert_called_once_with("cal", "cal stale", "warn")
```

- [ ] **Step 2: Run — FAIL** (`AttributeError: _update_strip_owner`).
- [ ] **Step 3: Implement in `ui.py`.**
  - Module import near the top with the other local imports:
    ```python
    import status_strip as _strip
    from status_strip import StatusStrip
    ```
  - In `__init__`, immediately after `self._install_raster_mode_controls()`:
    ```python
        # --- Always-visible annunciator strip (2026-08-12 redesign) ---
        self.status_strip = StatusStrip(self.statusBar())
        self._cal_collecting = None      # (collected, required) while calibrating
        self._cal_from_file = False      # last cal came from a loaded file
        self._cal_geometry_at_ready = None  # geometry snapshot for fresh cals
        self._strip_refresh_all()
    ```
  - In `__init__`, after `self._start_camera()`:
    ```python
        # Slow strip refresh: fps staleness + cal-stale re-check. CoarseTimer
        # on the GUI thread (never PreciseTimer on Windows). Also the safety
        # net that self-heals any cal-chip transition a hook missed.
        self._strip_watchdog = QtCore.QTimer(self)
        self._strip_watchdog.setTimerType(QtCore.Qt.CoarseTimer)
        self._strip_watchdog.setInterval(2000)
        self._strip_watchdog.timeout.connect(self._update_strip_slow)
        self._strip_watchdog.start()
    ```
  - New methods (place after `_update_armed_pending_status`):
    ```python
    # -------------------------
    # Status strip updates (display-only; never raise)
    # -------------------------

    def _update_strip_owner(self) -> None:
        text, state = _strip.owner_state(
            bool(getattr(self, "_raster_active_ui", False)),
            getattr(self, "_last_raster_source", None))
        self.status_strip.set_chip("owner", text, state)

    def _update_strip_progress(self) -> None:
        if getattr(self, "_raster_active_ui", False):
            idx = int(getattr(self.controller, "_raster_index", 0))
            total = int(getattr(self.controller, "_raster_total_steps", 0))
        else:
            idx = total = 0
        self.status_strip.set_chip("progress", _strip.progress_text(idx, total))

    def _update_strip_motor(self, mx, my) -> None:
        self.status_strip.set_chip("motor", _strip.motor_text(mx, my))

    def _update_strip_cal(self) -> None:
        has_cal = getattr(self.controller, "calibration", None) is not None
        # getattr: _strip_refresh_all runs early in __init__, before
        # _loaded_cal_bundle_camera_settings is assigned further down.
        bundled = (getattr(self, "_loaded_cal_bundle_camera_settings", None)
                   if self._cal_from_file else self._cal_geometry_at_ready)
        stale = has_cal and _strip.geometry_stale(
            self._get_cal_bundled_camera_settings(), bundled)
        text, state = _strip.cal_state(
            has_cal, self._cal_collecting, self._cal_from_file, stale)
        self.status_strip.set_chip("cal", text, state)

    def _update_strip_pending(self) -> None:
        # Same count-compare rule as _update_armed_pending_status: coarse,
        # but identical to the existing operator-facing contract.
        active = bool(getattr(self, "_raster_active_ui", False))
        show = False
        if active and self._raster_preview_pts:
            show = len(self._raster_preview_pts) != len(self.controller.armed_path_points())
        self.status_strip.set_warning("pending", show)

    def _update_strip_slow(self) -> None:
        stalled = (time.perf_counter() - self._last_frame_time) > 3.0
        text, state = _strip.fps_text(self._fps_smoothed, stalled)
        self.status_strip.set_chip("fps", text, state)
        self._update_strip_cal()

    def _strip_refresh_all(self) -> None:
        self._update_strip_owner()
        self._update_strip_progress()
        self.status_strip.set_chip("shots", _strip.shots_text(None))
        self.status_strip.set_chip("motor", _strip.motor_text(None, None))
        self.status_strip.set_chip("fps", "cam —", "idle")  # watchdog corrects
        self._update_strip_cal()
        self.status_strip.set_warning(
            "bounds", not self.enforce_bounds_checkbox.isChecked())
    ```
  - Hook the existing slots (add ONE line each at the end of the method unless stated):
    - `_on_raster_state`: `self._update_strip_owner(); self._update_strip_progress(); self._update_strip_pending()`
    - `_on_raster_source`: replace the whole `raster_source_label` text/stylesheet if/elif block with `self._update_strip_owner()` (keep `self._last_raster_source = source` and `self._update_step_mode_ui()`).
    - `_on_raster_shots_per_step`: body becomes `self.status_strip.set_chip("shots", _strip.shots_text(n))`.
    - `_on_target_position`: add `self._update_strip_progress()` at the end (set_chip's changed-text guard absorbs the ~4 Hz idle poll).
    - `_on_calibration_progress`: add `self._cal_collecting = (collected, required) if collected < required else None` then `self._update_strip_cal()`.
    - `_on_calibration_ready`: add `self._cal_collecting = None; self._cal_from_file = False; self._cal_geometry_at_ready = self._get_cal_bundled_camera_settings(); self._update_strip_cal()`.
    - `_on_calibration_failed`: add `self._cal_collecting = None; self._update_strip_cal()`.
    - `note_loaded_cal_bundle`: add `self._cal_from_file = True; self._update_strip_cal()`.
    - `_on_use_last_calibration`: add `self._cal_from_file = True; self._update_strip_cal()` after the load succeeds.
    - `_on_raster_param_changed`: add `self._update_strip_pending()`.
    - `_on_enforce_bounds_toggled`: add `self.status_strip.set_warning("bounds", not self.enforce_bounds_checkbox.isChecked())`.
    - `_on_save_history_toggled`: add at the end `self.status_strip.set_warning("rec", self._pos_history_file is not None)`; same line at the end of `_close_pos_history_file`.
  - In `_install_raster_mode_controls`: delete the `raster_source_label` and `raster_shots_label` creation blocks and the `self._on_raster_source(None)` / `self._on_raster_shots_per_step(None)` initial calls (grid rows 3/x free up — move `raster_rearm_button` from row 4 to row 3 and update its comment). `_on_raster_source`/`_on_raster_shots_per_step` now touch only the strip, which exists before any controller signal can fire.
- [ ] **Step 4: Run — PASS**

```bash
python -m pytest tests/test_ui_redesign_wiring.py tests/test_status_strip.py -q
python -m py_compile ui.py
```

- [ ] **Step 5: Commit**

```bash
git add ui.py tests/test_ui_redesign_wiring.py
git commit -m "feat(ui): annunciator status strip — owner/progress/shots/motor/cal/fps + warning chips

Replaces the remote group's source/shots labels; cal chip gains
collecting/file/stale states (stale = live geometry vs cal-bundled
geometry, watchdog-refreshed); REC/BOUNDS OFF/PATH EDITED chips."
```

---

### Task 7: `theme.py` — dark instrument-console QSS + palette

**Files:**
- Create: `theme.py`
- Modify: `main_rastering.py`
- Modify: `raster_gui.ui` (dynamic `primary` property on 5 buttons)
- Modify: `ui.py` (2 lines: `primary` property on the programmatic arm button; group-title-free chips need nothing)
- Test: `tests/test_status_strip.py` (extend with one QSS smoke test)

**Interfaces:**
- Consumes: chip labels named `chip_*` with `chipState` property (Task 5); dynamic bool property `primary` on `start_button`, `stop_button`, `path_button`, `calibrateButton` (in `.ui`) and `raster_remote_arm_button` (programmatic).
- Produces: `theme.PALETTE` (dict of the 6 spec tokens + semantic colors), `theme.build_qss(mono: str) -> str`, `theme.apply_theme(app) -> None`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_status_strip.py`:

```python
def test_theme_qss_covers_every_chip_state():
    import theme
    qss = theme.build_qss("Consolas")
    for state in ("idle", "good", "cyan", "warn", "alert"):
        assert f'chipState="{state}"' in qss, f"QSS missing chip state {state}"
    for token in ("#161A20", "#12151A", "#3EB4C8", "#E2A83D", "#52BE6E", "#E15A4D"):
        assert token in qss, f"QSS missing palette token {token}"
```

- [ ] **Step 2: Run — FAIL** (`ModuleNotFoundError: theme`).
- [ ] **Step 3: Implement `theme.py`:**

```python
"""Dark instrument-console theme (2026-08-12 redesign).

One QSS stylesheet from six palette tokens + Fusion dark QPalette.
Approved visual spec: docs/superpowers/specs/2026-08-12-rastering-ui-redesign-design.md
(parent repo). Qt QSS has no text-transform/letter-spacing -- group titles
are written uppercase-free in the .ui and styled by color/weight only.
"""
from __future__ import annotations

PALETTE = {
    "graphite": "#161A20",   # window ground
    "panel":    "#1E242C",   # group boxes, dock
    "recess":   "#12151A",   # camera well, input wells, status bar
    "line":     "#313A44",
    "ink":      "#D9E0E7",
    "muted":    "#8794A1",
    "cyan":     "#3EB4C8",   # interactive emphasis + armed state ONLY
    "cyan_dim": "#2A7D8C",
    "amber":    "#E2A83D",   # annunciator warn
    "green":    "#52BE6E",   # annunciator good
    "red":      "#E15A4D",   # annunciator alert (REC)
}


def build_qss(mono: str) -> str:
    p = PALETTE
    return f"""
QMainWindow, QDialog {{ background: {p['graphite']}; }}
QWidget {{ color: {p['ink']}; }}
QGroupBox {{
    background: {p['panel']};
    border: 1px solid {p['line']};
    border-radius: 3px;
    margin-top: 9px;
    padding-top: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    color: {p['muted']};
    font-weight: 600;
    font-size: 11px;
}}
QTabWidget::pane {{ border: 1px solid {p['line']}; }}
QTabBar::tab {{
    background: {p['recess']};
    color: {p['muted']};
    padding: 5px 16px;
    border: 1px solid {p['line']};
    border-bottom: none;
}}
QTabBar::tab:selected {{
    background: {p['graphite']};
    color: {p['ink']};
    border-bottom: 2px solid {p['cyan']};
}}
QPushButton {{
    background: {p['panel']};
    border: 1px solid {p['line']};
    border-radius: 3px;
    padding: 4px 10px;
}}
QPushButton:hover {{ border-color: {p['muted']}; }}
QPushButton:pressed {{ background: {p['recess']}; }}
QPushButton:disabled {{ color: {p['muted']}; border-color: {p['line']}; }}
QPushButton[primary="true"] {{
    color: {p['cyan']};
    border-color: {p['cyan_dim']};
    font-weight: 600;
}}
QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox {{
    background: {p['recess']};
    border: 1px solid {p['line']};
    border-radius: 3px;
    padding: 2px 5px;
    font-family: "{mono}";
}}
QTextEdit, QPlainTextEdit {{
    background: {p['recess']};
    border: 1px solid {p['line']};
    font-family: "{mono}";
    font-size: 11px;
}}
QStatusBar {{
    background: {p['recess']};
    border-top: 1px solid {p['line']};
}}
QStatusBar QLabel {{
    font-family: "{mono}";
    font-size: 11px;
    font-weight: 600;
    border: 1px solid {p['line']};
    border-radius: 3px;
    padding: 2px 8px;
    margin: 1px 2px;
}}
QLabel[chipState="idle"]  {{ color: {p['muted']}; }}
QLabel[chipState="good"]  {{ color: {p['green']}; border-color: {p['green']}; }}
QLabel[chipState="cyan"]  {{ color: {p['cyan']};  border-color: {p['cyan_dim']}; }}
QLabel[chipState="warn"]  {{ color: {p['amber']}; border-color: {p['amber']}; }}
QLabel[chipState="alert"] {{ color: {p['red']};   border-color: {p['red']}; }}
QMenuBar {{ background: {p['graphite']}; }}
QMenuBar::item:selected {{ background: {p['panel']}; }}
QMenu {{ background: {p['panel']}; border: 1px solid {p['line']}; }}
QMenu::item:selected {{ background: {p['recess']}; color: {p['cyan']}; }}
QProgressBar {{ background: {p['recess']}; border: 1px solid {p['line']}; }}
QDockWidget {{ background: {p['panel']}; }}
"""


def apply_theme(app) -> None:
    from PyQt5 import QtGui
    from PyQt5.QtGui import QFontDatabase

    app.setStyle("Fusion")
    p = PALETTE
    pal = QtGui.QPalette()
    c = QtGui.QColor
    pal.setColor(QtGui.QPalette.Window, c(p["graphite"]))
    pal.setColor(QtGui.QPalette.WindowText, c(p["ink"]))
    pal.setColor(QtGui.QPalette.Base, c(p["recess"]))
    pal.setColor(QtGui.QPalette.AlternateBase, c(p["panel"]))
    pal.setColor(QtGui.QPalette.Text, c(p["ink"]))
    pal.setColor(QtGui.QPalette.Button, c(p["panel"]))
    pal.setColor(QtGui.QPalette.ButtonText, c(p["ink"]))
    pal.setColor(QtGui.QPalette.ToolTipBase, c(p["panel"]))
    pal.setColor(QtGui.QPalette.ToolTipText, c(p["ink"]))
    pal.setColor(QtGui.QPalette.Highlight, c(p["cyan"]))
    pal.setColor(QtGui.QPalette.HighlightedText, c(p["recess"]))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, c(p["muted"]))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, c(p["muted"]))
    app.setPalette(pal)

    mono = "Cascadia Code" if "Cascadia Code" in QFontDatabase().families() else "Consolas"
    app.setStyleSheet(build_qss(mono))
```

- [ ] **Step 4: Apply it.** In `main_rastering.py`, right after `app = QtWidgets.QApplication(sys.argv)`:

```python
    from theme import apply_theme
    apply_theme(app)
```

In `raster_gui.ui`, add to each of `start_button`, `stop_button`, `path_button`, `calibrateButton`:

```xml
<property name="primary" stdset="0"><bool>true</bool></property>
```

In `ui.py` `_install_raster_mode_controls`, after creating `raster_remote_arm_button`:

```python
            self.raster_remote_arm_button.setProperty("primary", True)
```

- [ ] **Step 5: Run — PASS**

```bash
python -m pytest tests/test_status_strip.py -q
python -c "from PyQt5 import uic; uic.loadUiType('raster_gui.ui'); print('ui OK')"
python -m py_compile ui.py theme.py main_rastering.py
```

- [ ] **Step 6: Commit**

```bash
git add theme.py main_rastering.py raster_gui.ui ui.py tests/test_status_strip.py
git commit -m "feat: dark instrument-console theme — Fusion + token QSS, primary buttons, chip lamps"
```

---

### Task 8: Full verification + docs

**Files:**
- Modify: `CLAUDE.md` (rastering repo — Key Files section)
- No code changes expected; fix-forward anything the smoke run surfaces (each fix = its own small commit).

- [ ] **Step 1: Full camera-safe suite + syntax + ui checks**

```bash
cd "/c/Users/radmo/labscript-suite/GUIs/rastering-ui-redesign"
source ~/miniconda/etc/profile.d/conda.sh && conda activate rastering
python -m pytest tests/test_raster_pathmodel.py tests/test_zmq_v2_protocol.py \
    tests/test_raster_gui_ui_structure.py tests/test_status_strip.py -q
python -m py_compile ui.py status_strip.py theme.py main_rastering.py
python -c "from PyQt5 import uic; uic.loadUiType('raster_gui.ui'); print('ui OK')"
```
Expected: all green.

- [ ] **Step 2: Camera-caveat suites** — ONLY if the rastering GUI is not running and the camera is free (ask the operator if unsure):

```bash
python -m pytest tests/test_ui_slowdown_guards.py tests/test_ui_redesign_wiring.py -q
```

- [ ] **Step 3: Sim-mode smoke run** (motors simulated; camera errors log loudly but don't block):

```bash
RASTER_SIMULATE=1 python main_rastering.py
```
Manual checklist (~3 minutes, in the opened window):
  1. Three tabs Run / Pattern / Setup; dark theme applied; status strip shows `IDLE · pt — / — · — /pt · X … mm · cal — · cam —`.
  2. Run tab: jog buttons move the sim motor → motor chip updates numerically.
  3. Pattern tab: select `Spiral Raster` → spiral group appears; select `Square Raster X` → it hides. Change `xstep` → nothing crashes (pending chip only lights while armed).
  4. Uncheck `Enforce bounds` → `BOUNDS OFF` chip lights; re-check → it clears.
  5. Run tab: check `Save position history` → `● REC` lights; uncheck → clears.
  6. File menu → `Save current as defaults` logs "Saved current …" (Ctrl+D too).
  7. View menu still toggles the Camera Settings dock (Ctrl+Shift+C).
  8. Close the window → process exits cleanly (no traceback in the console).

- [ ] **Step 4: Update the rastering repo `CLAUDE.md`** Key Files list — add:

```markdown
- `status_strip.py` — annunciator status-strip chips (pure state functions + StatusStrip; camera-safe tests)
- `theme.py` — dark instrument-console QSS/palette, applied in main_rastering.py
```
and add `tests/test_raster_gui_ui_structure.py tests/test_status_strip.py` to the camera-safe test list in the Python Environment section.

- [ ] **Step 5: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md — status_strip/theme modules + new camera-safe tests"
```

- [ ] **Step 6: Report** — branch tip hash, test tally, smoke-checklist results. Merge to `main` is a SEPARATE decision (superpowers:finishing-a-development-branch); deployment is an operator GUI restart.

---

## Self-review notes (spec → plan)

- Every spec section maps: window frame/menu (Tasks 2–3), Run/Pattern/Setup tables (Tasks 2–3), spiral conditional (Task 4 — `setVisible` instead of `QStackedWidget`, same behavior, deliberate simplification), status strip incl. cal-stale + fps (Tasks 5–6 — fps reuses the existing `_fps_smoothed`; the spec's "new frame counter" is unnecessary), deletions table (Task 3), visual layer (Task 7), testing section (Tasks 2/4/5/6/8), rollout/worktree (Task 1).
- Spec's Setup table lists "User Home Both"; the approved Run-tab "Go user home" IS that widget (`user_home_both`) relabeled — one widget, one home (Task 3). Keeping a second Both button would recreate the duplicate-control problem this redesign kills.
- Group titles: Qt QSS supports neither `text-transform` nor `letter-spacing`; titles stay sentence-case in the `.ui`, styled muted/semibold via QSS (deviation from mockup's uppercase micro-labels, noted in `theme.py` docstring).
