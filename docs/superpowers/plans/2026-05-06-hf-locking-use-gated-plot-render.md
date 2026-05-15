# HF_Locking Use-Gated Plot Render — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skip the heavy `pyqtgraph.setData` per-frame work for HF_Locking channels whose `chk_use` checkbox is unchecked, clear the plot buffers when a user toggles `chk_use` off, AND reset the per-channel readouts (exposure label, amplitude bars, status badge) to a neutral "INACTIVE" state so a Use=off channel doesn't keep showing a stale green "Locked" badge. Cuts GUI-thread work 50-75% in typical operation (4 of 8 channels in use) while fixing a pre-existing UX bug.

**Architecture:** Two surgical edits to `class ChannelControl` in `GUIs/HF_Locking/display.py`. Edit 1 is an early-return guard at the top of `update_fast` so the timer-driven render path becomes a no-op for unused channels. Edit 2 extends `_on_switcher` (already wired to `chk_use.clicked`) — when Use is currently unchecked at click time, it clears the time/freq/volt deques, calls `setData([], [])` on both curves, resets `lbl_exp` / `bar_amp1` / `bar_amp2` / `status_label` to inactive defaults, AND invalidates the guarded-update caches (`_last_exp_text` / `_last_amp1` / `_last_amp2` / `_last_status_text`) so re-enabling triggers fresh `setText` calls. Both edits run on the Qt main thread, serialized with `_refresh_gui_fast`, so no race exists. See spec §"Why not gate just the plot block?" for why a simpler gate-only-the-plot-block approach was rejected (worker recycles `last_good` with `valid=True` to avoid -7 spikes, defeating the existing "NO SIGNAL" branch).

**Tech Stack:** Python 3.11, PyQt5, pyqtgraph. No unit-test framework in `GUIs/HF_Locking/` — verification is **manual against live hardware** (per project convention: `GUIs/HF_Locking/CLAUDE.md` "No unit tests — verification is manual against live hardware").

**Cleanup already done this session (NOT in this plan, listed for context):**
- Deleted `GUIs/HF_Locking/display_wide.py` (incomplete, no imports).
- Deleted `GUIs/HF_Locking/main_wlm_wide.py` (incomplete, no imports).
- Edited `GUIs/HF_Locking/CLAUDE.md` to remove the two table rows + 1 TODO entry for those files.
- These uncommitted changes will be bundled into the same submodule commit as the code edits in Task 4.

**Spec:** `docs/superpowers/specs/2026-05-06-hf-locking-use-gated-plot-render-design.md`

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `GUIs/HF_Locking/display.py` | Modify | All edits live here. `class ChannelControl`: `update_fast` (≈line 311) gets a 2-line guard; `_on_switcher` (≈line 510) gets a 6-line conditional clear block. |
| `GUIs/HF_Locking/main_wlm.py` | No change | The `_refresh_gui_fast` caller already iterates all channels — the no-op cost of an early-returning `update_fast` is negligible. |
| `GUIs/HF_Locking/CLAUDE.md` | Already modified | Wide-layout file-map + TODO rows removed earlier this session. Re-verify in Task 4 before commit. |

---

## Task 1: Add `chk_use` early-return guard in `update_fast`

**Files:**
- Modify: `GUIs/HF_Locking/display.py` (top of `ChannelControl.update_fast`, ≈line 311)

**Why this task is first:** The early return is the load-bearing performance change. Adding it on its own (without the buffer clear) leaves a usable intermediate state — channels with `chk_use=False` will simply freeze on their last frame. We verify perf behavior here, then layer the visual clear in Task 2.

- [ ] **Step 1: Re-read the current `update_fast` body to confirm the insertion point**

Open `GUIs/HF_Locking/display.py` and locate `def update_fast(self, meas: dict):` (≈line 311). The first executable statement should be `elapsed = time.perf_counter() - self._t0`. The new guard goes between the docstring and that line.

- [ ] **Step 2: Apply the edit**

Insert two lines immediately after the `update_fast` docstring (after the `"""` closer, before the first statement):

```python
        if not self.chk_use.isChecked():
            return
```

(Indentation: 8 spaces, matching method-body level.) No other lines in `update_fast` change.

- [ ] **Step 3: Verify by manual run — baseline (all Use=on)**

Activate the conda env and launch the GUI:

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python GUIs/HF_Locking/main_wlm.py
```

Expected: GUI launches normally, all 8 channels show smoothly scrolling plots at 30 Hz, both `[PRIORITY] Set to ABOVE_NORMAL` and `[POWER] EcoQoS execution-speed throttling disabled` print on startup. Click around — window stays responsive. **No regression.**

- [ ] **Step 4: Verify by manual run — Use=off intermediate behavior**

With the GUI still open, uncheck **Use** on one channel (e.g., Ch_1). Expected:
- That channel's two plots **freeze** on their last frame (this is the intermediate state — Task 2 turns this into a clear).
- Other channels keep updating normally.
- The frequency text label may also stop updating (depending on what else `update_fast` writes — that's fine).

Re-check Use → channel resumes plotting (it had already been removed from the WLM cycle for the duration; data populates from the next live measurement onward).

Close the GUI. **Do not commit yet** — Task 2 completes the feature before commit.

---

## Task 2: Clear plot + reset readouts + invalidate caches on Use-toggle-off in `_on_switcher`

**Files:**
- Modify: `GUIs/HF_Locking/display.py` (`ChannelControl._on_switcher`, ≈line 510)

**Why this task is second:** With Task 1 alone the user sees a frozen plot AND frozen readouts. The `update_fast` body at lines 404-443 also writes the exposure label, amplitude bars, and the colored "Locked"/"Unlocked"/"NO SIGNAL" status badge — none of which run after the early return. The fix is to perform a one-shot reset to inactive state on the toggle-off click, then invalidate the per-readout `_last_*` caches so re-enabling triggers fresh `setText` calls. Without cache invalidation the labels would stay stuck on "INACTIVE" forever because the guarded `if exp_text != self._last_exp_text` compares would suppress the new setText.

**Why not just gate the plot block?** A simpler-seeming alternative is to leave `update_fast` running but wrap only the plot-rendering portion in `if self.chk_use.isChecked():`. This does NOT work — the worker's `_normalize_frequency` (workers.py:212-214) recycles `last_good` with `valid=True` on `InfNothingChanged` to avoid -7 spikes, so a Use=off channel keeps reporting `valid=True` with the cached frequency and the existing "NO SIGNAL" branch never fires. See spec §"Why not gate just the plot block?".

- [ ] **Step 1: Re-read current `_on_switcher`**

Open `GUIs/HF_Locking/display.py` and find `def _on_switcher(self):` (≈line 510). Today its body is exactly one line:

```python
        self.request_switcher.emit(self.port, self.chk_use.isChecked(), self.chk_show.isChecked())
```

Verify this matches before editing — if it has diverged, stop and reconcile with the spec.

- [ ] **Step 2: Apply the edit**

Replace the one-line body with the full inactive-state block followed by the existing emit:

```python
    def _on_switcher(self):
        if not self.chk_use.isChecked():
            # Clear plot buffers
            self.t.clear()
            self.f.clear()
            self.v.clear()
            self.curve_freq.setData([], [])
            self.curve_volt.setData([], [])
            # Reset readouts so a Use=off channel doesn't show a stale "Locked" badge
            self.lbl_exp.setText("Exp: --")
            self.bar_amp1.setValue(0)
            self.bar_amp2.setValue(0)
            self.status_label.setText(
                f"<b>{self.name}: <span style='color:#7f8c8d'>INACTIVE</span></b>"
            )
            # Invalidate guarded-update caches so re-enable triggers fresh setText
            self._last_exp_text = None
            self._last_amp1 = -1
            self._last_amp2 = -1
            self._last_status_text = None
        self.request_switcher.emit(self.port, self.chk_use.isChecked(), self.chk_show.isChecked())
```

(Indentation: 4 spaces inside `def`, 8 spaces inside `if`. Match the method-header block depth.)

**Note on idempotency:** `_on_switcher` is also wired to `chk_show.clicked` (display.py:162). If the user clicks Show while Use is already off, the entire reset block re-runs. The deque clears + curve `setData([], [])` are harmless (already empty). The label `setText` calls write the same "INACTIVE" string they already show — Qt skips the actual paint when text is unchanged, so no flicker. Cache nulls stay nulled. All idempotent.

**Color choice:** `#7f8c8d` (gray) matches the existing **NO SIGNAL** styling at display.py:431 — same vocabulary for "quiescent state."

- [ ] **Step 3: Verify by manual run — toggle-off clears plot + sets INACTIVE readouts**

Launch the GUI with the conda command from Task 1, Step 3. Expected on Use-toggle-off of one channel:
- All 8 channels plot normally on launch.
- Uncheck Use on a channel → both `curve_freq` and `curve_volt` clear immediately (plot area empty, x/y axes still drawn).
- The exposure label changes to "Exp: --".
- Both amplitude bars drop to 0.
- The status label changes to a gray "<b>{Channel Name}: INACTIVE</b>".
- **Critical check:** if the channel was previously showing a green "Locked" badge, it must NOT keep showing "Locked" after the toggle. (This is the pre-existing UX bug we're fixing.)

- [ ] **Step 4: Verify by manual run — re-enable refreshes labels**

Re-check Use on the same channel. Expected:
- Plot starts populating from current time forward — no stale points from before the toggle-off.
- After the next worker poll (≤ 200 ms): exposure label updates to live "Exp: x+y ms" values, amp bars rise to live levels, status label updates to a fresh "Locked" / "Unlocked" / "NO SIGNAL" — **not** stuck on "INACTIVE."
- If the labels stayed on "INACTIVE", the cache invalidation in Step 2 was missed — re-check that all four `self._last_*` lines are present.

- [ ] **Step 5: Verify by manual run — `chk_show` does not trigger spurious changes (Use=on)**

With Use=on on a channel, click **Show** off, then on, then off again. Expected: the channel's plot continues displaying live data the whole time, and the status label keeps showing live state. (`_on_switcher` fires on Show clicks too, but the `if not chk_use.isChecked()` guard means none of the reset block runs while Use is on.)

- [ ] **Step 6: Verify by manual run — `chk_show` re-clicks while Use=off are idempotent**

With Use already OFF on a channel, click **Show** off then on then off. Expected: the channel stays in the "INACTIVE" state — gray label, "Exp: --", zero amp bars. No flicker, no error in console.

- [ ] **Step 7: Verify by manual run — config-restore path**

Restart the GUI. If `pid_config.json` persists a Use=False channel from the previous run, expected: that channel loads with an empty plot AND default constructor labels (NOT the "INACTIVE" string — because `set_status` uses `blockSignals(True)/blockSignals(False)` at display.py:469-473, so `_on_switcher` does not fire on config restore). No clear-flash, no error.

Close the GUI.

---

## Task 3: Optional throughput verification with diagnostics

**Files:**
- Modify (temporarily): `GUIs/HF_Locking/diagnostics.py` (line 1: `ENABLED = False` → `True`)

**Why optional:** Manual visual verification in Tasks 1-2 is sufficient to confirm functional correctness. This task quantifies the perf win for engineering confidence and to verify the assumption "50-75% reduction" in the spec. Skip if not interested.

- [ ] **Step 1: Enable diagnostics**

Edit `GUIs/HF_Locking/diagnostics.py` and flip `ENABLED = False` to `ENABLED = True`. Look for the constant near the top of the file.

- [ ] **Step 2: Capture baseline (all 8 channels Use=on)**

Launch the GUI, let it run for 30 s with all channels Use=on. Watch the console for `WARN_GUI_UPDATE_MS` lines (threshold = 20 ms per `docs/hf-locking-rates.md`). Note approximate count or rate.

Close the GUI.

- [ ] **Step 3: Capture reduced-load run (4 channels Use=off)**

Re-launch the GUI. Uncheck Use on 4 channels (any 4). Let run for 30 s. Watch the console for `WARN_GUI_UPDATE_MS`.

**Expected:** noticeably fewer warnings vs Step 2. If the rate did not drop, something is wrong — re-read Task 1 Step 2 to confirm the early return is in place and reachable. (Likely: typo in `chk_use.isChecked()`, or the guard was inserted into a sibling method.)

- [ ] **Step 4: Revert diagnostics flag**

Edit `GUIs/HF_Locking/diagnostics.py` and flip `ENABLED = True` back to `ENABLED = False`. **Do not commit diagnostics.py with `ENABLED=True`** — production default is off (per spec).

- [ ] **Step 5: Verify diagnostics is back off**

```bash
grep '^ENABLED' GUIs/HF_Locking/diagnostics.py
```

Expected output: `ENABLED = False`

---

## Task 4: Commit (HF_Locking submodule, then parent repo)

**Files:**
- Stage in HF_Locking submodule: `display.py`, `CLAUDE.md`, plus the two file deletions (`display_wide.py`, `main_wlm_wide.py`).
- Stage in parent repo: `docs/superpowers/specs/2026-05-06-hf-locking-use-gated-plot-render-design.md`, `docs/superpowers/plans/2026-05-06-hf-locking-use-gated-plot-render.md`, plus the submodule pointer update for `GUIs/HF_Locking`.

**Why two commits:** Per `CLAUDE.md` "Commit to each repo separately. Do not push without asking." `GUIs/HF_Locking/` is its own git repo (submodule); parent labscript-suite repo tracks the submodule pointer.

- [ ] **Step 1: Confirm HF_Locking submodule status is clean of unrelated edits**

```bash
git -C GUIs/HF_Locking status
```

Expected:
- `modified: display.py` (from Tasks 1-2)
- `modified: CLAUDE.md` (cleanup done earlier this session)
- `deleted: display_wide.py` (already done this session)
- `deleted: main_wlm_wide.py` (already done this session)
- Nothing else.

If diagnostics.py shows modified, re-run Task 3 Step 4.

- [ ] **Step 2: Commit in HF_Locking submodule**

```bash
git -C GUIs/HF_Locking add display.py CLAUDE.md
git -C GUIs/HF_Locking rm display_wide.py main_wlm_wide.py
git -C GUIs/HF_Locking commit -m "$(cat <<'EOF'
Skip update_fast and clear curves when channel Use is off

Cuts pyqtgraph setData per-frame work 50-75% with typical 2-4 of 8
channels in use. Adds early return at top of update_fast and clears
deques + curves when chk_use is unchecked at click-time. Also drops
the incomplete display_wide.py / main_wlm_wide.py wide-layout
variants and their entries in CLAUDE.md.

Spec: docs/superpowers/specs/2026-05-06-hf-locking-use-gated-plot-render-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git -C GUIs/HF_Locking status
```

Expected: `working tree clean`.

- [ ] **Step 3: Confirm parent repo status**

```bash
git status
```

Expected modified paths:
- `GUIs/HF_Locking` (submodule pointer bumped to the new commit from Step 2)
- New: `docs/superpowers/specs/2026-05-06-hf-locking-use-gated-plot-render-design.md`
- New: `docs/superpowers/plans/2026-05-06-hf-locking-use-gated-plot-render.md`

(Pre-existing modified/untracked entries from prior sessions are fine — leave them alone.)

- [ ] **Step 4: Commit in parent repo**

```bash
git add GUIs/HF_Locking docs/superpowers/specs/2026-05-06-hf-locking-use-gated-plot-render-design.md docs/superpowers/plans/2026-05-06-hf-locking-use-gated-plot-render.md
git commit -m "$(cat <<'EOF'
HF_Locking: gate plot rendering on chk_use to cut per-frame work

Bumps GUIs/HF_Locking submodule pointer to the use-gated-render
commit, and adds the design spec + implementation plan that drove it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git status
```

Expected: parent commit success, submodule pointer updated. Pre-existing untracked/modified files from earlier sessions remain — that's normal.

- [ ] **Step 5: Final smoke test**

Relaunch the GUI one last time:

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python GUIs/HF_Locking/main_wlm.py
```

Expected:
1. Window opens, all channels with Use=on plot smoothly.
2. Uncheck Use on a channel → plot clears immediately.
3. Re-check Use → plot starts populating from now.
4. Window stays responsive throughout (no "Not Responding").
5. BLACS-side `LaserLockDevice` (if BLACS is running) keeps receiving ZMQ updates — no regression on the REQ-REP / PUB-SUB protocol.

If any of those fail, **do not push**. Reopen the spec, re-run the failing verification, and triage.

---

## Self-Review Checklist Results

- **Spec coverage:** Every spec section maps to a task — Decision §1 → Task 1, Decision §2 → Task 2, Verification steps 1-3 → Task 1+2 manual checks, step 4 (config persistence) → Task 2 Step 5, step 5 (throughput) → Task 3, step 6 (no regression) → Task 4 Step 5. Files Changed entries map to Task 4 staging.
- **Placeholder scan:** No "TBD", "TODO", "implement later", or vague "handle edge cases". All edits show exact lines. Manual-verification steps state expected outcomes concretely.
- **Type/identifier consistency:** `chk_use` / `chk_show`, `curve_freq` / `curve_volt`, `t`/`f`/`v` deques, `_on_switcher`, `update_fast`, `request_switcher` all match across tasks and the spec verbatim.
- **Adapted TDD:** Project has no pytest infrastructure for this GUI. TDD-shaped steps replaced with run-launch-observe verifications, in keeping with `GUIs/HF_Locking/CLAUDE.md` "verification is manual against live hardware".
