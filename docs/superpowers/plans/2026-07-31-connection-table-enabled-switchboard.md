# Connection Table ENABLED Switchboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the comment-out-150-lines workflow in `connection_table.py` with a per-BLACS-tab `ENABLED` dict of grouped `if` blocks, plus a generic even-DO parity pad.

**Architecture:** One module-level `ENABLED` dict (importable by sequences); each hardware component's devices grouped in one `if ENABLED['name']:` block inside `connection_table()`; a `_pad_even_digitals(card)` helper runs after all blocks and adds a dummy DO on a reserved spare line if a card's DO count is odd. A small compile harness (`tools/compile_ct.py`) makes every step testable without RunManager or hardware.

**Tech Stack:** Python 3.11 (conda env `labscript`), labscript 3.x (`labscript_init`/`start`/`stop`), h5py.

**Spec:** `docs/superpowers/specs/2026-07-31-connection-table-enabled-switchboard-design.md`

## Global Constraints

- Every Python command needs conda activation: `source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python ...` (bare `python` is the wrong interpreter on this machine).
- All work is in the **parent repo** (`C:\Users\radmo\labscript-suite`). The working tree is shared/mixed — commit with `git add <your files>` then `git commit --only <your files>`; never `git add .`; never push.
- Compiling a connection table is pure software — no hardware, BLACS, or RunManager needed until the final manual task.
- Initial `ENABLED` values MUST mirror today's file: `ni_6361/ni_6535/ni_scope/camera = False`, `laser_lock/rastering/bigsky = True`. The refactor must produce a byte-identical device list to the pre-refactor compile (Task 2 verifies).
- The PrawnBlaster (`pb`) gets **no** switch — BLACS requires the master pseudoclock unconditionally.
- No hardcoded dependency pairs and no wiring warnings — per spec, a disabled dependency fails naturally with `NameError`, and cable-only links (NI_SCOPE trigger) are accepted as silent-at-runtime.
- Preserve the original in-code comments when reviving commented blocks (they carry operational knowledge, e.g. Nuvu timeout rationale).

---

### Task 1: Compile harness `tools/compile_ct.py`

**Files:**
- Create: `userlib/labscriptlib/Main_Experiment/tools/compile_ct.py`

**Interfaces:**
- Produces (used by Tasks 2–3): CLI `python tools/compile_ct.py [switch=0|1 ...]` — compiles `connection_table.py` into a throwaway h5, applying any `switch=value` overrides to the module's `ENABLED` dict, then prints `COMPILE OK` plus the sorted names of every row in the compiled connection table. Exit 0 on success, nonzero (traceback) on compile failure.

- [ ] **Step 1: Write the harness**

```python
"""Compile connection_table.py outside RunManager/BLACS.

Usage (labscript conda env, from userlib/labscriptlib/Main_Experiment/):
    python tools/compile_ct.py                     # file's own ENABLED values
    python tools/compile_ct.py ni_6535=1 camera=1  # override switches for this run

Prints COMPILE OK + every device/channel name in the compiled connection
table. Exit 0 on success. Each run uses a fresh process and a throwaway h5,
so labscript's compiler state is always clean.
"""
import os
import sys
import tempfile

# userlib root (contains labscriptlib/ and user_devices/) must be importable,
# same as RunManager arranges via labconfig.
USERLIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, USERLIB)

import labscript  # noqa: E402  (imports labscript_utils.h5_lock before h5py)
import h5py  # noqa: E402
from labscript import start, stop  # noqa: E402

CT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'connection_table.py')
)


def main():
    overrides = {}
    for arg in sys.argv[1:]:
        key, sep, val = arg.partition('=')
        if not sep or val not in ('0', '1'):
            sys.exit(f"bad argument {arg!r} — expected switch=0 or switch=1")
        overrides[key] = bool(int(val))

    run_file = os.path.join(tempfile.mkdtemp(), 'ct_compile_check.h5')
    # runmanager-style run file: just needs a globals group
    with h5py.File(run_file, 'w') as f:
        f.create_group('globals')

    labscript.labscript_init(
        run_file, labscript_file=CT_PATH, load_globals_values=False
    )
    import labscriptlib.Main_Experiment.connection_table as ct_mod

    enabled = getattr(ct_mod, 'ENABLED', None)
    if overrides:
        if enabled is None:
            sys.exit("this connection_table.py has no ENABLED dict — no overrides possible")
        unknown = set(overrides) - set(enabled)
        if unknown:
            sys.exit(f"unknown switches: {sorted(unknown)} — valid: {sorted(enabled)}")
        enabled.update(overrides)

    ct_mod.connection_table()
    start()
    stop(1.0)
    labscript.labscript_cleanup()

    with h5py.File(run_file, 'r') as f:
        names = sorted(row['name'].decode() for row in f['connection table'][:])
    print('COMPILE OK — connection table rows:')
    for name in names:
        print('  ' + name)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run it against the CURRENT (pre-refactor) file**

```bash
cd /c/Users/radmo/labscript-suite/userlib/labscriptlib/Main_Experiment
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript
python tools/compile_ct.py
```

Expected: exit 0, `COMPILE OK`, and a row list containing `pb`, `LaserLockGUI`, `Vexlum_Setpoint`, `TiSa_1_Setpoint`, `TiSa_2_Setpoint`, `TiSa_1_Value`, `TiSa_2_Value`, `RasteringGUI`, `Raster_X`, `Raster_Y`, `Raster_X_Monitor`, `Raster_Y_Monitor`, `BigSkyLasers` plus BigSkyHub auto-created channels and PrawnBlaster internal clocklines. No NI devices, no camera, no scope.

If this fails, fix the harness (not the connection table) until it passes — the connection table is known-good today.

- [ ] **Step 3: Verify the override guard fails cleanly pre-refactor**

```bash
python tools/compile_ct.py camera=1
```

Expected: exit nonzero with `this connection_table.py has no ENABLED dict` (the dict doesn't exist until Task 2).

- [ ] **Step 4: Commit**

```bash
cd /c/Users/radmo/labscript-suite
git add userlib/labscriptlib/Main_Experiment/tools/compile_ct.py
git commit --only userlib/labscriptlib/Main_Experiment/tools/compile_ct.py -m "Add compile_ct.py harness for connection table compile checks

- tools/compile_ct.py: NEW — compiles connection_table.py into a throwaway
  h5 outside RunManager/BLACS, with optional ENABLED switch overrides;
  prints the compiled row list for before/after diffing."
```

---

### Task 2: Refactor `connection_table.py` to the ENABLED switchboard

**Files:**
- Modify: `userlib/labscriptlib/Main_Experiment/connection_table.py` (full rewrite of contents, 222 lines today)

**Interfaces:**
- Consumes: `tools/compile_ct.py` CLI from Task 1.
- Produces: module-level `ENABLED` dict with keys `ni_6361, ni_6535, ni_scope, camera, laser_lock, rastering, bigsky` (importable by sequences); module-level `_pad_even_digitals(card)` helper; `connection_table()` signature unchanged (no args, returns None).

- [ ] **Step 1: Capture the pre-refactor baseline**

```bash
cd /c/Users/radmo/labscript-suite/userlib/labscriptlib/Main_Experiment
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript
python tools/compile_ct.py > /tmp/ct_before.txt && cat /tmp/ct_before.txt
```

Expected: same output as Task 1 Step 2.

- [ ] **Step 2: Replace the entire contents of `connection_table.py` with:**

```python
from labscript import *
from labscriptlib.Main_Experiment.subsequences.subsequences import digital_pulse
from labscript_devices.PrawnBlaster.labscript_devices import PrawnBlaster
from labscript_devices.NI_DAQmx.models.NI_PXIe_6361 import NI_PXIe_6361
from labscript_devices.NI_DAQmx.models.NI_PXIe_6535 import NI_PXIe_6535
from user_devices.RemoteControl.labscript_devices import RemoteAnalogOut, RemoteAnalogMonitor
from user_devices.LaserLockDevice.labscript_devices import LaserLockDevice
from user_devices.RasteringDevice.labscript_devices import RasteringDevice
from user_devices.BigSkyHub.labscript_devices import BigSkyHub
from user_devices.NuvuCamera.labscript_devices import NuvuCamera
# The NI_SCOPE import lives inside its ENABLED block below, so a disabled
# scope costs no module import (mirrors the previously commented-out import).

# ═══ Hardware switchboard — one entry per BLACS tab ═══════════════════════
# Flip a value → recompile the connection table in RunManager → restart BLACS.
# The PrawnBlaster has no switch: BLACS requires the master pseudoclock.
# A block referencing a device from a disabled block fails at compile time
# with a NameError naming the missing device — that is the intended guard.
ENABLED = dict(
    ni_6361    = False,  # NI PXIe-6361 analog card + daq_ai/daq_ao channels
    ni_6535    = False,  # NI PXIe-6535 digital card + YAG/ENH lines
    ni_scope   = False,  # NI PXIe-5922 digitizer
    camera     = False,  # Nuvu EMCCD (trigger parent: ni_6535 port0/line0)
    laser_lock = True,   # HF_Locking GUI
    rastering  = True,   # Rastering GUI
    bigsky     = True,   # BigSky YAG hub
)

# Reserved spare line per NI card for even-children padding.
PARITY_PAD_LINE = {
    'ni_6361': 'port0/line0',  # no DOs on the 6361 today — pad never fires
    'ni_6535': 'port0/line4',  # the historical 'dummy_line'
}


def _pad_even_digitals(card):
    """NI-DAQmx requires an even number of DO children per card
    (NI_DAQmx labscript_devices._check_even_children). Count the DOs that
    actually ended up on the card — including auto-created Trigger lines,
    since Trigger subclasses DigitalOut — and add one dummy DO on the
    card's reserved spare line if the count is odd."""
    n_do = sum(isinstance(child, DigitalOut) for child in card.child_devices)
    if n_do % 2:
        DigitalOut(f'parity_pad_{card.name}', card, PARITY_PAD_LINE[card.name])


def connection_table():
    # === Initialize pseudoclock (always on — master clock) ===
    pb = PrawnBlaster(
        name='pb',
        com_port='COM4',
        num_pseudoclocks=2
    )

    # === NI 6361 Setup ===
    if ENABLED['ni_6361']:
        ni_6361_max_name = "PXI1Slot8"

        ni_6361 = NI_PXIe_6361(
            name='ni_6361',
            parent_device=pb.clocklines[0],  # Pseudoclock 0
            clock_terminal=f'/{ni_6361_max_name}/PFI1',
            MAX_name=f'{ni_6361_max_name}',
            acquisition_rate=100e3,
            stop_order=-1,
            AI_term='Diff',
            num_AI=6,
            num_AO=2
        )

        AnalogIn('daq_ai0', ni_6361, 'ai0')
        AnalogIn('daq_ai1', ni_6361, 'ai1')
        AnalogIn('daq_ai2', ni_6361, 'ai2')
        AnalogIn('daq_ai3', ni_6361, 'ai3')
        AnalogIn('daq_ai4', ni_6361, 'ai4')
        AnalogIn('daq_ai5', ni_6361, 'ai5')

        AnalogOut('daq_ao0', ni_6361, 'ao0')  # Used for NI-5922 TRIG
        AnalogOut('daq_ao1', ni_6361, 'ao1')  # not used

    # === NI 6535 Setup ===
    if ENABLED['ni_6535']:
        ni_6535_max_name = "PXI1Slot5"

        ni_6535 = NI_PXIe_6535(
            name='ni_6535',
            parent_device=pb.clocklines[1],  # Pseudoclock 1
            clock_terminal=f'/{ni_6535_max_name}/PFI4',  # adjust if needed
            MAX_name=ni_6535_max_name,
            stop_order=1
        )

        # Digital output lines on PXIe-6535
        DigitalOut('YAG1_line', ni_6535, 'port0/line1')
        DigitalOut('YAG2_trig', ni_6535, 'port0/line2')
        DigitalOut('ENH_line', ni_6535, 'port0/line3')

        # no latched lines in open-cell CT -- line0 is now the camera trigger (was LIF_shutter)
        ni_6535.set_property('latched_lines', [], location='device_properties')

    # === NI_SCOPE (PXIe-5922 digitizer) ===
    if ENABLED['ni_scope']:
        from user_devices.NI_SCOPE.labscript_devices import NI_SCOPE
        NI_SCOPE(
            name='NI_SCOPE',
            MAX_name='PXI1Slot2',
            vertical_range=[0.5, 0.1],       # Vpp for [Ch0, Ch1]
            vertical_coupling=['DC', 'DC'],  # Supported strings: 'DC', 'AC', 'GND', 'HF_REJECT', 'LF_REJECT'. (Need to check if working..)
            min_sample_rate=1_000_000,       # Hz
            min_num_pts=200_000,             # record length
            trigger_source='TRIG',
            trigger_level=1.0,               # triggers at +1V
            trigger_delay=0.0,               # 0s time offset between trigger event and when sampling starts
            channels_to_save=[0, 1],         # which NI-5922 channels to save to h5
        )

    # === Nuvu Camera ===
    # NOTE: The initialization of the NuvuCamera creates an implicit DO under
    # the name "camera_trigger" at the specified connection.
    if ENABLED['camera']:
        camera = NuvuCamera(
            name="camera",
            parent_device=ni_6535,
            connection="port0/line0",
            serial_number=0xDEADBEEF,  # NUVU camera initialization does not require serial_number, no need to touch this
            camera_attributes={
                "readoutMode": 1,  # 1 = EM
                "exposure_time": 20,  # Shafin: "Um miliseconds?"
                "timeout": 5000,  # ms; SDK frame-wait before error 214 — must outlast normal arm-to-trigger latency; grab_multiple retries on expiry
                "square_bin": 1,  # NxN bin size
                'target_detector_temp': -60,
                "emccd_gain": 500,  # Max 5000
                "trigger_mode": 2,  # 1 = EXT_LOW_HIGH, #0 = INT, 2 "EXT_LOW_HIGH_EXP" (minus for HIGH_LOW),
                "shutter_mode": 1,
            },
            manual_mode_camera_attributes={
                "readoutMode": 1,
                "exposure_time": 20,
                "timeout": 5000,
                "square_bin": 1,
                'target_detector_temp': -60,
                "emccd_gain": 500,
                "trigger_mode": 0,  # INT in manual mode so snap/continuous self-trigger (Lyman convention); buffered attrs above set 2 = EXT per shot
                "shutter_mode": 1,
            },
            mock=False  # True
        )

    # === Laser Lock Communication === #
    if ENABLED['laser_lock']:
        LaserLockDevice(name='LaserLockGUI', host="127.0.0.1", reqrep_port=3796, pubsub_port=3797, mock=False, wait_for_lock=True)

        # Name convention: <wavemeter channel>_Setpoint and <wavemeter channel>_Value

        RemoteAnalogOut(
            name='Vexlum_Setpoint',
            parent_device=LaserLockGUI,
            connection=3,
            units="THz",
            decimals=9
        )

        RemoteAnalogOut(
            name='TiSa_1_Setpoint',
            parent_device=LaserLockGUI,
            connection=1,
            units="THz",
            decimals=9
        )

        RemoteAnalogOut(
            name='TiSa_2_Setpoint',
            parent_device=LaserLockGUI,
            connection=6,
            units="THz",
            decimals=9
        )

        RemoteAnalogMonitor(
            name='TiSa_1_Value',
            parent_device=LaserLockGUI,
            connection=1,
            units="THz",
            decimals=9
        )

        RemoteAnalogMonitor(
            name='TiSa_2_Value',
            parent_device=LaserLockGUI,
            connection=6,
            units="THz",
            decimals=9
        )

    # === Rastering GUI Communication === #
    if ENABLED['rastering']:
        RasteringDevice(
            name='RasteringGUI',
            host="127.0.0.1",
            reqrep_port=55535,
            pubsub_port=55536,
            mock=False,
        )

        RemoteAnalogOut(
            name='Raster_X',
            parent_device=RasteringGUI,
            connection="laser_raster_x_coord",
            units="mm",
            limits=(0, 25.0),
            decimals=4,
            step_size=0.001,
        )

        RemoteAnalogOut(
            name='Raster_Y',
            parent_device=RasteringGUI,
            connection="laser_raster_y_coord",
            units="mm",
            limits=(0, 25.0),
            decimals=4,
            step_size=0.001,
        )

        RemoteAnalogMonitor(
            name='Raster_X_Monitor',
            parent_device=RasteringGUI,
            connection="laser_raster_x_coord_monitor",
            units="mm",
            limits=(0, 25.0),
            decimals=4,
        )

        RemoteAnalogMonitor(
            name='Raster_Y_Monitor',
            parent_device=RasteringGUI,
            connection="laser_raster_y_coord_monitor",
            units="mm",
            limits=(0, 25.0),
            decimals=4,
        )

    # === BigSky YAG Laser Communication === #
    if ENABLED['bigsky']:
        BigSkyHub(name='BigSkyLasers', num_lasers=1, laser_prefix="YAG", host="127.0.0.1")
        # All channels auto-created

    # === Even-children padding ===
    # Runs after ALL blocks so auto-created Trigger lines (camera) are counted.
    if ENABLED['ni_6361']:
        _pad_even_digitals(ni_6361)
    if ENABLED['ni_6535']:
        _pad_even_digitals(ni_6535)

    return


if __name__ == '__main__':
    # Begin issuing labscript primitives
    connection_table()
    # start() elicits the commencement of the shot
    start()

    # Stop the experiment shot with stop()
    stop(1.0)
```

Notes for the implementer:
- The `LaserLockGUI`, `RasteringGUI` names used as `parent_device=` are valid bare names because labscript injects every named device into builtins at creation — this is how the original file already works. Do not "fix" it.
- `camera` is assigned but unused — the original did the same; keep it.
- `digital_pulse` is imported but unused — the original did the same; keep it.
- The YAG/ENH `DigitalOut` lines and `latched_lines` property were commented out in the pre-refactor file *only because the whole 6535 section was*; they belong to the card and are part of its block.

- [ ] **Step 3: Compile with default switches and diff against baseline**

```bash
cd /c/Users/radmo/labscript-suite/userlib/labscriptlib/Main_Experiment
python tools/compile_ct.py > /tmp/ct_after.txt
diff -u /tmp/ct_before.txt /tmp/ct_after.txt && echo IDENTICAL
```

Expected: `IDENTICAL` (zero diff — the refactor changed nothing for today's configuration). Any diff is a bug in the refactor; fix before proceeding.

- [ ] **Step 4: Verify a disabled-dependency failure is a readable NameError**

```bash
python tools/compile_ct.py camera=1
```

Expected: exit nonzero, traceback ending in `NameError: name 'ni_6535' is not defined` (camera enabled, its trigger parent disabled — the designed guard).

- [ ] **Step 5: Commit**

```bash
cd /c/Users/radmo/labscript-suite
git add userlib/labscriptlib/Main_Experiment/connection_table.py
git commit --only userlib/labscriptlib/Main_Experiment/connection_table.py -m "Refactor connection_table.py to per-tab ENABLED switchboard

- connection_table.py: replace commented-out device blocks with permanent
  code behind an ENABLED dict (one key per BLACS tab; defaults mirror the
  previous comment state, compile verified identical) — flipping a flag +
  recompile + BLACS restart replaces hand-editing ~150 lines
- connection_table.py: add _pad_even_digitals() — counts DO children per
  NI card (Trigger lines included) after all blocks and pads with a dummy
  DO on a reserved spare line (port0/line4 on the 6535, the historical
  dummy_line) to satisfy the NI-DAQmx even-children rule in every
  switch combination"
```

⚠️ `git status` will also show pre-existing modifications to `BaF_globals.h5`, `Open_cell2.py`, and possibly others — they are NOT part of this work. `--only` protects against committing them; do not stage them.

---

### Task 3: Prove the revived blocks and the parity pad

The commented-out blocks were frozen while the rest of the codebase evolved; this task turns them on in compile-only mode and fixes whatever rot surfaces.

**Files:**
- Modify (only if stale references surface): `userlib/labscriptlib/Main_Experiment/connection_table.py`

**Interfaces:**
- Consumes: `tools/compile_ct.py` CLI (Task 1); `ENABLED` switch names (Task 2).

- [ ] **Step 1: Compile with everything on**

```bash
cd /c/Users/radmo/labscript-suite/userlib/labscriptlib/Main_Experiment
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript
python tools/compile_ct.py ni_6361=1 ni_6535=1 ni_scope=1 camera=1
```

Expected: exit 0. Row list must include `ni_6361`, `daq_ai0`–`daq_ai5`, `daq_ao0`, `daq_ao1`, `ni_6535`, `YAG1_line`, `YAG2_trig`, `ENH_line`, `NI_SCOPE`, `camera`, `camera_trigger` — and must NOT include `parity_pad_ni_6535` (DO count on the 6535 is 4: YAG1 + YAG2 + ENH + camera_trigger — already even).

If this fails with a stale-code error (changed import path, renamed kwarg, etc.): fix the minimal thing inside the failing block — argument values and structure must stay as-committed unless the compile literally rejects them. Record every such fix in the Task 3 commit message.

- [ ] **Step 2: Verify the pad fires when the camera is off**

```bash
python tools/compile_ct.py ni_6361=1 ni_6535=1
```

Expected: exit 0, and the row list now INCLUDES `parity_pad_ni_6535` (DO count was 3 → padded to 4) and contains no `camera` / `camera_trigger`.

- [ ] **Step 3: Re-verify the default config is still untouched**

```bash
python tools/compile_ct.py > /tmp/ct_after2.txt
diff -u /tmp/ct_before.txt /tmp/ct_after2.txt && echo IDENTICAL
```

Expected: `IDENTICAL`. (If Step 1 required no file changes, this is trivially true; run it anyway.)

- [ ] **Step 4: Commit (only if Step 1 required fixes)**

```bash
cd /c/Users/radmo/labscript-suite
git add userlib/labscriptlib/Main_Experiment/connection_table.py
git commit --only userlib/labscriptlib/Main_Experiment/connection_table.py -m "Fix stale references in revived connection table blocks

- connection_table.py: <one bullet per fix found in Task 3 Step 1, naming
  the block and what was stale>"
```

If no fixes were needed, skip the commit and state so.

---

### Task 4: Document the convention + manual lab verification

**Files:**
- Modify: `.claude/rules/sequences.md` (append one bullet to the conventions list)

**Interfaces:**
- Consumes: `ENABLED` dict semantics from Task 2.

- [ ] **Step 1: Append to the bullet list in `.claude/rules/sequences.md`** (after the "Connection table does NOT have access to RunManager globals" bullet):

```markdown
- **ENABLED switchboard**: `connection_table.py` gates each BLACS tab behind a module-level `ENABLED` dict (PrawnBlaster excepted — always on). Workflow: flip flag → recompile CT → restart BLACS. Sequences may `from labscriptlib.Main_Experiment.connection_table import ENABLED` to branch on hardware presence. Even-DO padding is automatic (`_pad_even_digitals`); never add manual dummy DO lines.
```

- [ ] **Step 2: Commit**

```bash
cd /c/Users/radmo/labscript-suite
git add .claude/rules/sequences.md
git commit --only .claude/rules/sequences.md -m "Document ENABLED switchboard convention in sequences rule

- .claude/rules/sequences.md: add ENABLED-dict convention (flip flag ->
  recompile -> restart BLACS; sequences may import ENABLED; parity padding
  is automatic)"
```

- [ ] **Step 3: Manual lab verification (USER runs these — hardware/GUI territory)**

Present this checklist to the user; do not attempt to run BLACS or RunManager yourself:

1. RunManager → recompile the connection table (default flags) → expect clean compile.
2. RunManager → compile `sequences/Open_cell2.py` → expect clean compile (its device usage matches the default config, which is unchanged).
3. Restart BLACS → expect the exact same tab set as before the refactor (LaserLockGUI, RasteringGUI, BigSkyLasers, pb).
4. Run one test shot → confirm h5 output lands normally.

Per repo convention: connection table changes = compile + restart BLACS; after any BLACS change = test shot + h5 check.

---

## Self-Review (done at plan-writing time)

- **Spec coverage:** ENABLED dict → Task 2; grouped blocks + mirror defaults → Task 2 (Step 3 proves "identical"); NameError guard → Task 2 Step 4; parity pad + reserved line → Task 2 (code) + Task 3 (proof); revival of frozen blocks → Task 3; sequences-fail-loud needs no code (verified behavior); deferred items (presets/GUI/no-restart) correctly absent; workflow + docs → Task 4.
- **Placeholder scan:** the only intentionally open content is Task 3's fix-what-surfaces commit bullet — unavoidable (contents unknowable until the compile runs) and bounded by the "minimal fix, record it" rule.
- **Type consistency:** `ENABLED` keys identical across Tasks 1–4; `_pad_even_digitals(card)` name consistent; harness CLI identical everywhere.
