# HF_Locking — Follow-ups Surfaced During 2026-05-12 Verification

**Date:** 2026-05-12
**Status:** Open — items deferred from the use-gated render commit
**Scope:** Items found during hardware verification of the use-gated plot-render optimization (see [2026-05-06-hf-locking-use-gated-plot-render-design.md](2026-05-06-hf-locking-use-gated-plot-render-design.md)) that are out of scope for that commit but worth tracking.

## Item 1 — Auto-exposure requires `chk_show=True` (WS7 hardware behavior)

**Symptom (observed 2026-05-12):** after toggling `chk_use` ON for a channel, the WS7 wavemeter did not adjust exposure. Auto-exposure only kicked in once `chk_show` was also enabled.

**Mechanism:** WS7 firmware only runs auto-exposure for channels visible in the WLM UI. `Use=True` puts a port into the switcher cycle, but `Show=True` is required for the WLM to run its exposure-adjustment loop. This is documented WS7 behavior — see [pylablib's HighFinesse driver notes](https://pylablib.readthedocs.io/en/latest/devices/HighFinesse.html) which mentions a related quirk where exposure changes are not reported until the WLM UI is switched to a given channel.

**Not a code bug.** Our code correctly passes `(use, show)` to `wlm.set_switcher_signal` ([wlm_utils.py:49](GUIs/HF_Locking/wlm_utils.py#L49)).

**Action:** add a one-line note to [GUIs/HF_Locking/CLAUDE.md](GUIs/HF_Locking/CLAUDE.md) under a "WS7 quirks" or "Known Hardware Behavior" section. Fix size: 1 line. Priority: low (documentation only).

## Item 2 — Window resizes slightly when first channel enables in a column

**Symptom (observed 2026-05-12):** the GUI window expands slightly when the first channel in a column is enabled. Nominal window size with no channels running differs from the size when a channel has data.

**Mechanism:** pyqtgraph viewbox layout reflow on the first `setData()` call. Plot widgets start at `setMinimumHeight(90)` with autorange disabled ([display.py:159-164](GUIs/HF_Locking/display.py#L159-L164)); the first data point triggers an internal viewbox bounds-compute that adjusts the size hint, propagating up the column. **Plausibly worsened** by the 2026-05-12 use-gated render change (empty `setData([], [])` on Use=off means the empty→populated transition is more visible), but the underlying behavior is pre-existing.

**Fix candidate (4 lines, deferred):** set explicit Y-ranges in `ChannelControl.__init__` so pyqtgraph's first-data bounds compute doesn't change the size hint:

```python
self.plot_freq.setYRange(-10, 10, padding=0)
self.plot_volt.setYRange(-200, 200, padding=0)
```

These get immediately overridden by the autoscale logic when real data arrives and `chk_auto_y` is checked — they're just startup defaults to lock the layout. No user-visible behavior change.

**Action:** apply in a future session if/when prioritized. Fix size: ~4 lines. Priority: low (cosmetic, marked low priority by user 2026-05-12).

## Item 3 — WS7 voltage-output behavior when `Use=False` (documentation gap)

**Symptom (observed 2026-05-12):** unclear what the WLM does with the per-channel voltage output when a port is excluded from the switcher cycle (`Use=False`). Re-enabling the channel does restore the voltage setpoint, but the off-period behavior is undocumented.

**What's known:** our code calls `SetSwitcherSignal(port, 0, show)` ([wlm_utils.py:49](GUIs/HF_Locking/wlm_utils.py#L49)) to disable the port and reads back via `get_switcher_signal`. The WS7 manual ([`Manual WS7 NeLAC (1).pdf`](../../Manual WS7 NeLAC (1).pdf)) does not explicitly document voltage-output behavior for disabled ports.

**Industry expectation:** "hold last output" — common in feedback systems where dropping output mid-lock would cause loss. Less likely: "disable/float output."

**Action:** empirical bench test in a future session — set a known voltage, disable the port via `Use=False`, monitor the physical output line. Then update CLAUDE.md or this doc with the verdict. Fix size: 0 lines code, ~5 lines doc. Priority: medium (operationally relevant, but the channel re-enable already restores correct state).

## Cross-references

- Commit that surfaced these: HF_Locking submodule commit landing on or about 2026-05-12, "Skip update_fast and reset readouts when channel Use is off" (see [2026-05-06-hf-locking-use-gated-plot-render-design.md](2026-05-06-hf-locking-use-gated-plot-render-design.md)).
- Audit agents that characterized each item: see session transcript 2026-05-12.
