# Moving a Laser Between Wavemeter Channels (WS7)

Procedure + full blast radius for moving laser **X** from WS7 channel **A** to channel **B**.
Derived from the 2026-07-29 TiSa_1 ch4 → ch1 move (crosstalk); audited against code that day.
Line numbers WILL rot — re-derive with Step 0, don't trust them blind.

## The one hardware fact that drives everything

The HF_Locking GUI **forces PID DAC output index == measurement channel index**:
`wlm_utils.py set_channel_assignment(port, enable)` writes `cmiDeviationChannel[port] = port`,
and the lock readback only reports locked when that equality holds. So moving a laser's
measurement fiber to channel B means its analog lock output moves to **rear-panel output B**
— the SMA cable must physically follow. (The DLL itself would allow cross-routing via the
WS7 native app, but the GUI has no UI for it and its lock indicator would read unlocked
forever. Don't.)

## Step 0 — Re-derive the target list

The parent `.gitignore` excludes `GUIs/`, so a repo-root grep **silently skips the GUI**.
Grep all four trees explicitly:

```
C:\Users\radmo\labscript-suite                        (master)
C:\Users\radmo\labscript-suite\GUIs\HF_Locking        (main — the live GUI)
C:\Users\radmo\labscript-suite\GUIs\HF_Locking-zmq-v2 (zmq-v2-port)
C:\Users\radmo\labscript-suite\.claude\worktrees\*    (parent topic branches)
```

Patterns: the laser name; `CHANNEL_NAMES|LOCK_TOLERANCE|_BY_PORT|lock_tolerance`;
`ch<A>|channel <A>|port <A>|conn <A>|connection ?= ?<A>|parent_port='<A>'`;
`cmiDeviationChannel|set_channel_assignment|DeviationChannel`.

## Step 1 — GUI code (`GUIs/HF_Locking/`, 2 edits)

- `main_wlm.py` `CHANNEL_NAMES` — swap the names for A and B.
- `workers.py` `LOCK_TOLERANCE_BY_PORT` — re-key any tolerance override from A to B.
- Everything else is port-generic (loops `PORTS`, resolves names via `CHANNEL_NAMES.get`).
  If a new port-keyed dict has appeared since 2026-07, the Step 0 patterns find it.
- Cosmetic: the channel's panel tile moves — grid position is `((port-1)//2, (port-1)%2)`.

## Step 2 — Tests (`GUIs/HF_Locking/tests/test_lock_invariants.py`)

- Re-key H1's `LOCK_TOLERANCE_BY_PORT ==` dict and its `lock_tolerance(A)/lock_tolerance(B)`
  pair; re-key H2b's `run(A, …)`/`run(B, …)` calls AND its function name.
- **Check every other test for implicit tolerance assumptions.** A test using an offset
  sized for the 5 MHz default on a channel that just acquired a 1 MHz override goes
  *silently vacuous* instead of failing (happened to H2 in the 2026-07 move; its offset
  is now 2e-7 THz, inside every tolerance).
- Run `pytest tests -q` in the **`guis`** conda env. Mock-based, safe with GUI running.

## Step 3 — BLACS connection table (`userlib/labscriptlib/Main_Experiment/`)

- `connection_table.py` — update **both** children: `RemoteAnalogOut(name='X_Setpoint')`
  AND `RemoteAnalogMonitor(name='X_Value')`. They deliberately share one `connection`;
  changing only one silently breaks output↔monitor pairing in `LaserLockDevice/blacs_tabs.py`.
- Backup tables (`connection_table_closed_cell2.py`, …) are not loaded by BLACS — update
  only if you want them restorable as-is.
- Device classes need **no** change: `LaserLockDevice`/`RemoteControl` are pure
  `parent_port` pass-through. Sequences reference `X_Setpoint` by name — channel-agnostic.
- ZMQ PUB topics re-derive from the connection number on both ends — no wire-format change.

## Step 4 — Docs

Update live assertions; **leave dated observations alone** (annotate "(chA at the time)").
Live-assertion files as of 2026-07: root `CLAUDE.md` (HF lock spec), `docs/hf-locking-rates.md`,
`docs/external-guis-architecture.md`, `docs/main-experiment-overview.md`,
`docs/device-internals.md` + `.claude/memory-backup/device-internals.md`,
`docs/matisse-c-external-locking.md` (many lines), `docs/shot-h5-layout.md`
(`child_connections` list), `GUIs/HF_Locking/CLAUDE.md`,
`GUIs/HF_Locking/.claude/agents/pid-persistence.md`.
Historical (don't renumber): `notes/*.html`, `docs/superpowers/{specs,plans}/`, dated shot analyses.

## Step 5 — Other branches/worktrees (merge-regression risk)

`git worktree list` in each repo; grep every branch. A branch still holding channel A
**regresses the fix on merge**. As of 2026-07-29:
- `zmq-v2-cutover` worktree: `connection_table.py` still `connection=4` (both children) —
  must be fixed before/at merge. Its docs are double-stale (flat tolerance + ch4).
- `HF_Locking-zmq-v2` branch: has NO `LOCK_TOLERANCE_BY_PORT`/`lock_tolerance()` at all
  (flat constant; `display.py` has its own local `LOCK_TOL`) while its CLAUDE.md claims
  otherwise. Rebase must port the per-channel mechanism (keyed to the NEW channel) and
  the H1/H2b test assertions. Expect conflicts in workers.py, display.py, tests.
- `docs/matisse-external-lock-commissioning.md` exists ONLY on zmq-v2-cutover (3 ch4 refs).

## Step 6 — Wavemeter internals + hardware (nothing in git covers this)

In order:
1. **Backup WLM** button (copies wlm_ws7.ini, WLM8407ST.stn, history.8407 →
   `wlm_backups/<timestamp>/`; restore is manual).
2. **Save Config** button — records all 8 ports' live PID state to `pid_config.json`
   so the pre-move tuning of channel A is on file.
3. **Disarm channel A's lock** in the GUI (writes `cmiDeviationChannel[A] = 0`) BEFORE
   moving the fiber, so A's PID can't integrate against whatever lands there next.
4. Move the **fiber** A → B.
5. Move the **PID output SMA cable** rear-panel output A → output B (see coupling above).
   The step most likely to be forgotten; nothing in software detects it missing.
6. Migrate per-channel settings A → B inside the WS7 (native app or one-off script; there
   is no migration tool — `config.restore_settings` is same-port only). The full set is the
   registries in `config.py`: PID gains (P/I/D/T/dt), Sensitivity*, Polarity, Unit, UseTa,
   Constdt, ClearHistory*, Bounds, RefAt/RefMid, Setpoint (`GetPIDCourseNum`).
   **Two traps:**
   - `DeviationChannel` is the ONE setting whose value is itself a channel number —
     re-point it to B, never copy A's value.
   - `pid_config.json` snapshots taken while unlocked store `DeviationChannel: 0` for
     every port; a wholesale restore disarms all locks. Restore selectively.
7. Re-arm B's lock; confirm the global Deviation toggle is ON (if off, `PROGRAM_VALUE`
   returns SUCCESS without waiting — the known silent lock-bypass). Verify exposure on B.
8. **Save Config** again so `pid_config.json` reflects the new layout.

## Step 7 — Verify end-to-end

1. Compile connection table in RunManager → restart BLACS.
2. Expect ONE saved-state mismatch dialog on first BLACS start (saved AO values are keyed
   by connection string; channel B's stale value surfaces once). Accept the remote value.
   Do NOT delete the BLACS saved-state h5.
3. Test shot → confirm the h5 writes `remote_device_operation['B']` and `monitor_values`
   columns show B. Restart the HF GUI and check the lock indicator on B.
