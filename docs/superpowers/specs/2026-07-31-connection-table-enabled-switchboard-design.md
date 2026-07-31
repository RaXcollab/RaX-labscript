# Connection Table ENABLED Switchboard — Design

**Date:** 2026-07-31
**Status:** Awaiting user approval
**Scope:** `userlib/labscriptlib/Main_Experiment/connection_table.py` only

## Problem

Running the experiment with a subset of hardware currently means commenting out
~150 lines of `connection_table.py` (NI cards, AnalogIns, NI_SCOPE, NuvuCamera).
This is error-prone, hard to diff, and makes each hardware configuration an
ad-hoc edit instead of a declared state.

## Design

### 1. ENABLED dictionary

One dictionary at the top of `connection_table.py`, one key per nominal BLACS
tab:

```python
ENABLED = dict(
    ni_6361    = False,  # NI_PXIe_6361 analog card + daq_ai0-5 AnalogIns
    ni_6535    = False,  # NI_PXIe_6535 digital card
    ni_scope   = False,  # NI_SCOPE digitizer
    camera     = False,  # NuvuCamera (trigger parent currently on ni_6535)
    laser_lock = True,   # LaserLockDevice + channels
    rastering  = True,   # RasteringDevice + Raster_X/Y
    bigsky     = True,   # BigSkyHub
)
```

- **No PrawnBlaster entry** — BLACS requires the master pseudoclock to exist
  unconditionally (`blacs/experiment_queue.py` uses it directly).
- **Initial values mirror the current file** (commented blocks = False), so the
  first compile after the refactor produces the same connection table as today.

### 2. Grouped `if` blocks (no nesting, no registry)

Each component's code is grouped into one labeled block wrapped in
`if ENABLED['<name>']:`. The currently commented-out blocks become permanent
live code behind their switches. Channels belonging to a component (e.g. the
daq_ai AnalogIns) live inside that component's block — adding a channel to an
existing component needs no new wrapping; only a brand-new tab needs a new dict
entry + block.

### 3. Cross-component dependencies: fail naturally

No hardcoded dependency pairs (e.g. no `camera requires ni_6535` assertion —
the camera could be retriggered differently later). If an enabled block
references a device from a disabled block, compilation fails with Python's own
`NameError: name 'ni_6535' is not defined`, which already names the missing
device. That is the guard. Blocks appear in dependency order in the file
(cards first, then devices that hang off them).

**Interrelated devices — two cases:**

- **Link declared in the CT** (e.g. NuvuCamera `parent_device=ni_6535`,
  connection_table.py:175, which auto-creates the `camera_trigger` DO):
  caught at compile time by the `NameError` guard above. Loud and early.
- **Link that is only a physical cable** (e.g. NI_SCOPE `trigger_source='TRIG'`
  — its own front-panel BNC, fed by an NI line labscript knows nothing about):
  invisible to compilation, before and after this refactor. Scope-on +
  card-off compiles fine and fails silently at runtime (no trigger → timeout /
  empty trace).

Both outcomes accepted as-is (user decision 2026-07-31). No dependency
comments, wiring dict, or warning machinery will be added.

### 4. Even-children parity: generic post-pass

The NI_DAQmx even-children rule (`labscript_devices/NI_DAQmx/labscript_devices.py:388-399`)
requires an even count of DO children per card — including invisible
auto-created Trigger lines (the camera adds one). This is general to all
digital lines, not camera-specific. So:

- After all enabled blocks have run, a small helper counts DigitalOut-type
  children (DigitalOut + Trigger subclasses) on each enabled NI card.
- If the count is odd, it instantiates one dummy DO on a **reserved spare
  line**, declared as a per-card constant (e.g.
  `PARITY_PAD_6535 = 'port3/line7'` — exact free line chosen during
  implementation from the wiring map).
- AO counts are currently even (2 on the 6361) and stable; the same pattern
  extends to AO if ever needed. Not implemented now.

### 5. Sequences

- Unchanged by default. A sequence referencing a disabled device fails at
  RunManager compile time with `NameError` — no shot file is generated, nothing
  reaches hardware.
- Optionally, a sequence can branch on the switchboard to serve multiple
  configs from one file:

```python
from labscriptlib.Main_Experiment.connection_table import ENABLED, connection_table
connection_table()
...
if ENABLED['camera']:
    # camera exposure block
```

## Workflow after landing

Flip a value in `ENABLED` → recompile connection table in RunManager → restart
BLACS. (Restart-free toggling was verified feasible but is explicitly out of
scope — see below.)

## Out of scope (deferred, by user decision)

- Named presets / multiple configs, text-file config, checkbox GUI — the
  ENABLED dict is the foundation any of these would sit on.
- No-restart per-shot subset toggling ("superset in BLACS, subset per shot").
  Verified possible with caveats (POST_EXP stranding, byte-identical device
  rows); revisit only if restarts become a burden.

## Verification plan

1. **No-change check:** compile with the default (today-equivalent) flags;
   confirm RunManager compiles clean and BLACS loads the same tab set as
   before the refactor.
2. **Revival check:** compile with all flags True — the commented-out blocks
   have been frozen while the file evolved, so this validates them as live
   code again (fix stale names as found).
3. **Parity check:** compile a combination with an odd DO count to confirm the
   pad line is created and `_check_even_children` passes.
4. **Sequence check:** compile `Open_cell2.py` against the default config.
5. Restart BLACS on the default config and run a test shot.
