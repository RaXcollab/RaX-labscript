# Matisse C-S External Lock — Parallel Investigation Runbook

Phased lab procedure to **test multiple lock architectures in parallel**
against the same shot pattern + failure metrics, pick the empirical winner.
No pre-selected favorite. See [matisse-c-external-locking.md](matisse-c-external-locking.md)
for architecture descriptions, configuration tables, and the corrected
failure mechanism (§6 of that doc).

## Candidates

| Tag | Architecture | Cable | Internal ref-cell lock |
|---|---|---|---|
| **W** | Current WS7-direct PID (baseline) | Rear item 13 | ON |
| **C** | Counterdrift plug-in (Matisse Commander) | Rear item 13 (same as W) | ON |
| **A** | DSP External Input bypass | Front item 4 (cable moved) + switch Extern | OFF |
| **G** | GoTo plug-in overlay on top of W / C / A | (no cable change) | Per underlying candidate |

## Acceptance test (run identically for W, C, A, A+G)

**Test shot pattern:** 100 shots, BLACS sequence, sub-MHz step resolution,
5–10 MHz hops in arbitrary order within a ~500 MHz envelope around the
production setpoint for TiSa_1 (ch4, ~348.666 THz).

**Metrics captured per run** (write to
`docs/commissioning-logs/2026-MM-DD-phaseN-{w,c,a,g}.txt`):

| Metric | How measured | Threshold to "win" |
|---|---|---|
| Lock-loss count | Count `FASTPIEZO:LOCK?` FALSE transitions during shots | ≤ 1 per 100 |
| σ at fixed setpoint (10-min hold before scan) | Std-dev of WS7 reading | ≤ 1 MHz |
| Settling time per step | Setpoint write → WS7 within 1 MHz of target | ≤ 200 ms |
| Mode-hop events | WS7 reading jumps > 100 MHz from target | 0 per 100 |
| Slow Piezo search invocations | `SLOWPIEZO:NOW?` velocity changes consistent with FREESPEED sweep | 0 per 100 |
| Max σ during scan | Std-dev of WS7 reading around moving target | ≤ 5 MHz |
| Operator-actionable cost | Subjective recovery effort | Whatever's least painful |

Winner is **Pareto-frontier across these metrics**, not single-axis max.

## Pre-checks (record once before Phase 0; needed for ALL phases)

| Item | Command / location | Recorded |
|---|---|---|
| Matisse firmware | `*IDN?` via Matisse Commander | ≥ 1.4 |
| WS7 calibration date | WS7 GUI status bar | within last 24 h |
| Current Fast Piezo gains | `FPZT:CNTRPROP?` `FPZT:CNTRINT?` | factory ref-cell values |
| Current Slow Piezo gains | `SPZT:LPROP?` `SPZT:LINT?` `SPZT:FREESPEED?` | factory ref-cell values |
| Current WS7 PID config (ch4) | `pid_config.json` in `GUIs/HF_Locking/` | P=0.16, I=0.84, D=0.034, T=0.02, dt=0.01, Polarity=-1, SensitivityDim=-2 |
| Current TiSa_1 setpoint | WS7 ch4 `cmiPIDCourse` | ~348.666 THz |
| Front-panel DSP switch (item 3) | Visual | **Intern** (expected) |
| Cable destination | Visual trace | Rear item 13 (Reference Cell external) |
| BiFi calibration valid? | `Plug-ins > Wavemeter > Birefringent Filter Calibration` table loaded | Yes / No |
| Control Scan Measurement done? | `Scan > Control Scan Measurement` last-run date | Yes / No |

Take photos of HF_Locking GUI + Matisse Commander main window before any
change. All rollback procedures depend on this.

---

## Phase 0 — Baseline (Candidate W)

**Goal:** quantify current pain. Numbers to beat for all subsequent
candidates.

### Steps

1. Power on per normal startup procedure.
2. Tune to target wavelength via `Birefringent Filter > Scan` and
   `Thin Etalon > Scan` (Matisse Commander, Manual ch. 7).
3. Enable Thin Etalon and Piezo Etalon control loops.
4. Click `Main Window > Lock` to engage internal ref-cell lock.
5. Verify HF_Locking GUI's external WS7 servo is engaged for ch4
   (as in normal operation).
6. Hold for 10 min, log:
   - `FASTPIEZO:LOCK?` per second
   - `FASTPIEZO:NOW?` (tweeter) per second
   - `SLOWPIEZO:NOW?` per second
   - WS7 ch4 reading per ~200 ms
   - WS7 ch4 DAC voltage per ~200 ms

### Acceptance criteria for Phase 0

- [ ] At baseline (no scan running), `FASTPIEZO:LOCK?` stays TRUE for
      the full 10-min hold.
- [ ] σ of WS7 reading at fixed setpoint ≤ 5 MHz (loose floor — Phase 0
      is allowed to fail this; we're measuring the floor, not enforcing it).

If even the bare hold is unstable → don't proceed; the problem is upstream
of the architecture. Diagnose Piezo Etalon and ref-cell health first.

### Run the 100-shot scan test

7. Run the standard 100-shot BLACS sequence over the 500 MHz envelope
   (TiSa_1 production scan).
8. Capture all metrics from the acceptance table above.
9. Save log to `docs/commissioning-logs/2026-MM-DD-phase0-w.txt`.

### Output

Phase-0 metric values for Candidate W. These are what every other
candidate needs to beat.

### Rollback

None — this is the current production setup.

---

## Phase 1 — Counterdrift A/B (Candidate C)

**Goal:** test whether Sirah's Counterdrift safety features (soft-start,
AutoReset, Laser-Locked interlock) materially improve over W on the same
ref-cell-driven architecture. ~30 minutes of work.

Same session as Phase 0 if possible — no hardware changes.

### Switch from W to C

1. In HF_Locking GUI, **disable the WS7 PID for ch4**:
   - Via WS7 native app: Settings → Laser Control → uncheck "Active" for ch4
   - Or via DLL: `SetDeviationMode(0)` on port 4
2. In Matisse Commander:
   - `Matisse > Plug-ins`: ensure **HighFinesse** (or **WM Selector**)
     and **External PID** plug-ins are enabled (External PID isn't being
     tested but its presence doesn't interfere; only Counterdrift will
     be active).
   - Open `Plug-ins > Wavemeter > Counterdrift` dialog
3. Configure Counterdrift:
   - Unit: THz (or whatever Matisse Commander is set to)
   - Setpoint: write the TiSa_1 production setpoint (~348.666 THz)
   - PID: **P = 0, I = −0.5, D = 0, Average = 10**
   - Update Time: **300 ms** (≥ 200 ms required for 8-channel switched WS7)
   - `Synchronous Wavemeter Readout?` = **ON**
   - `AutoReset` = **OFF** initially (we want to observe rail behavior;
     do not let it auto-recover with GHz frequency jumps until we
     understand the behavior)
4. Click `Set to current position` (sets setpoint to current laser
   freq → makes initial error ≈ 0)
5. Verify `Main > Lock` still ON (internal ref-cell lock active —
   Counterdrift's "Laser Locked?" interlock requires it)
6. Click `Activate` on Counterdrift

### Sanity check

- [ ] Counterdrift "Laser Locked?" indicator green within 5 s
- [ ] Counterdrift "Control Output" trace stays bounded
- [ ] WS7 reading stays within ±5 MHz of setpoint for 60 s with no scan

### Run the 100-shot scan test

7. BLACS-side: temporarily redirect `PROGRAM_VALUE` for ch4 to Counterdrift
   setpoint instead of WS7 `SetPIDCourseNum`. (This may require a temporary
   patch in `LaserLockDevice` if VI Server access isn't already wired —
   or use Matisse Commander VI Server directly from a test script.)
8. Run the 100-shot sequence.
9. Capture metrics.
10. Save log to `docs/commissioning-logs/2026-MM-DD-phase1-c.txt`.

### Interpretation

- **If C beats W substantially:** Sirah's safety features matter. Worth
  staying in this architecture. Use Counterdrift production-ready.
- **If C ≈ W:** Architecture is the limit, not implementation. Expect
  A to beat both.
- **If C is worse than W:** Probably Counterdrift's interlock is dropping
  it more aggressively than W; rerun with logging tighter to isolate.

### Rollback to W

1. Click `Deactivate` on Counterdrift dialog
2. Re-enable WS7 PID for ch4:
   - Via WS7 native app: Settings → Laser Control → check "Active" for ch4
   - Or via DLL: `SetDeviationMode(1)` on port 4
3. Restore BLACS-side `PROGRAM_VALUE` routing to `SetPIDCourseNum`
4. Verify W operational

---

## Phase 2 — DSP External Input bypass (Candidate A)

**Goal:** test whether eliminating the internal ref-cell lock removes the
failure mode entirely. Separate session — needs hardware work.

### Hardware preparation

1. Power off Matisse pump laser **only**. Leave Matisse C control box on
   so you can monitor DSP voltages.
2. **Move the WS7 ch4 SMA cable** from rear-panel **Reference Cell
   external input (item 13)** to **front-panel DSP External Input SMA
   (item 4)**.
3. **Do not flip the Intern/Extern switch yet.** Leave it on Intern.
4. Apply physical label near item 3: **"EXTERN = WS7 deviation. Verify
   cable + signal before engaging FPZT lock."**

### WS7 deviation-mode configuration

Via HF_Locking GUI or wlmData DLL, edit `pid_config.json` for ch4:

```
P = 1.0
I = 0.0
D = 0.0
Average = 10
SensitivityDim = -2  (kept from current — scale ±500 MHz to ±2 V)
SensitivityFactor = 1.0
Polarity = -1  (keep current; flip to +1 if lock diverges on first attempt)
BoundsMin = -4000.0
BoundsMax = +4000.0
```

Reload config via HF_Locking GUI's Restore PID Config dialog (read-before-
write per the `pid-persistence` agent in
`GUIs/HF_Locking/.claude/agents/`).

### Sanity check error signal

1. **Keep front-panel switch on Intern.** WS7 DAC voltage is now present at
   item 4 but not selected.
2. With internal lock active and WS7 at production setpoint, observe:
   - Briefly flip switch (item 3) to **Extern**
   - Query `FASTPIEZO:INPUT?` — should read a normalized value within ±1
     (= ±5 V at the SMA), close to 0 if WS7 is near reference
   - Flip switch **back to Intern**
3. If `FASTPIEZO:INPUT?` reads exactly 0.0 or out-of-range, the cable is
   wrong or WS7 isn't outputting. Fix before proceeding.

### Engage external lock

1. `Main > Lock` **OFF** in Matisse Commander (disable internal ref-cell
   lock). `FASTPIEZO:CONTROLSTATUS` should read STOP.
2. Set initial Matisse Fast Piezo gains low:
   - `FASTPIEZO:CONTROLPROPORTIONAL` ← (recorded factory) / 10
   - `FASTPIEZO:CONTROLINTEGRAL` ← (recorded factory) / 10
3. Set initial Slow Piezo gains low:
   - `SLOWPIEZO:LOCKPROPORTIONAL` ← (recorded factory) / 10
   - `SLOWPIEZO:LOCKLINTEGRAL` ← (recorded factory) / 10
4. Set `FASTPIEZO:CONTROLSETPOINT 0.0` (lock at DSP input = 0V = WS7 at
   reference)
5. Set `FASTPIEZO:LOCKPOINT 0.0`
6. Flip front-panel switch (item 3) to **Extern**
7. `FASTPIEZO:CONTROLSTATUS RUN`
8. Watch Fast Piezo + Slow Piezo waveform displays

### Possible immediate outcomes

| Symptom | Cause | Action |
|---|---|---|
| Fast Piezo immediately rails 0 or 1 | Polarity wrong | `FPZT:CNTRSTA STOP`, flip Polarity in WS7 (`SetPIDSetting(cmiDeviationPolarity, 4, iSet=+1)`), `RUN` again |
| Fast Piezo oscillates rapidly | Gains too high | Reduce P + I by another factor of 2 |
| Lock acquires but WS7 drifts | Sensitivity wrong / Slow Piezo not following | Tune Slow Piezo gains up, or rescale WS7 sensitivity |
| Lock acquires and is steady | Continue to acceptance test | |

### Acceptance criteria

- [ ] `FASTPIEZO:LOCK?` TRUE for ≥ 10 minutes
- [ ] `FASTPIEZO:NOW?` between 0.2 and 0.8 (no rail drift)
- [ ] σ of WS7 reading ≤ 1 MHz around target

### Tuning recipe (if acceptance fails)

One parameter at a time:

1. **Slow oscillation at ~Hz:** Slow Piezo I too high — reduce
   `SLOWPIEZO:LOCKLINTEGRAL` by 30 %
2. **Fast oscillation at ~tens of Hz:** Fast Piezo P too high — reduce
   `FASTPIEZO:CONTROLPROPORTIONAL` by 30 %
3. **Lock acquires but drifts to rails:** Slow Piezo not catching up —
   increase `SLOWPIEZO:LOCKPROPORTIONAL` (or `LOCKLINTEGRAL`)
4. **WS7 reading noisy below detector resolution:** WS7 sensitivity too
   high — back off
5. **`FASTPIEZO:LOCK?` flickers FALSE:** tweeter near 95 % — adjust
   mechanical alignment or change `FASTPIEZO:CONTROLSETPOINT` to recenter

Document each iteration in the commissioning log.

### Per-shot scan test

Once steady lock holds:

1. From BLACS, call `SetDeviationReference(target + Δ)` with Δ =
   +50, +200, +500 MHz
2. Confirm `FASTPIEZO:LOCK?` stays TRUE across each step
3. Run the full 100-shot BLACS sequence
4. Capture metrics
5. Save log to `docs/commissioning-logs/2026-MM-DD-phase2-a.txt`

### Rollback to W

1. `FASTPIEZO:CONTROLSTATUS STOP`
2. Restore Fast Piezo + Slow Piezo gains to factory ref-cell values
3. Flip front-panel switch (item 3) **back to Intern**
4. `Main > Lock` ON in Matisse Commander
5. Re-enable WS7 PID for ch4 with original config (P=0.16, I=0.84, etc.)
6. Move SMA cable back from item 4 to item 13
7. Verify W operational

---

## Phase 3 — GoTo overlay (Candidate G)

**Optional, only if Phase 0-2 results justify it.** Indicated only if:
- A typical sequence requires hops > one Piezo Etalon mode (~18 GHz), OR
- Sub-mode hops still fail despite Phase 0-2 (suggesting BiFi/etalon
  miscoordination, not pure lock failure)

### Configuration

1. Confirm BiFi calibration + Control Scan Measurement done (pre-checks).
2. In BLACS `LaserLockDevice`, add a new method `goto_wavelength(target)`
   that:
   - Calls Matisse Commander `Plug-ins > Wavemeter > GoTo` via VI Server
   - Blocks until GoTo completes (typically seconds)
   - Reads back WS7 reading; verifies within 50 MHz of target
   - Engages whichever fine lock (W / C / A) is being tested
3. **This requires code changes** — out of scope for this commissioning
   round, deferred to follow-up session per the plan in
   `~/.claude/plans/read-the-manual-for-concurrent-newt.md`.

### Acceptance test (when implemented)

Use `goto_wavelength` as a per-shot pre-positioner. Run 100-shot
sequence at low shot rate (≤ 1 Hz, since GoTo takes seconds). Capture
metrics; expect much lower lock-loss but much higher per-shot latency.

---

## Phase 4 — Decision and commit

After Phases 0–2 (and optionally 3) complete:

| Metric | W (Phase 0) | C (Phase 1) | A (Phase 2) | A+G (Phase 3) | Winner |
|---|---|---|---|---|---|
| Lock-loss / 100 | _ | _ | _ | _ | |
| σ at fixed (MHz) | _ | _ | _ | _ | |
| Settling (ms) | _ | _ | _ | _ | |
| Mode-hops / 100 | _ | _ | _ | _ | |
| Search invocations / 100 | _ | _ | _ | _ | |
| Max σ scan (MHz) | _ | _ | _ | _ | |
| Operator cost | _ | _ | _ | _ | |

Pick the winner. Document in
`docs/commissioning-logs/2026-MM-DD-phase4-decision.md`.

### Production gains table (fill in after winner selected)

**Candidate W production config** _(if W wins — keep current)_:
- WS7 P / I / D = ___ / ___ / ___
- Sensitivity = ___
- Polarity = ___
- Bounds = ___ / ___

**Candidate C production config** _(if C wins)_:
- Counterdrift P / I / D = ___ / ___ / ___
- Average = ___
- Update Time = ___ ms
- Synced Readout = ON / OFF
- AutoReset = ON / OFF

**Candidate A production config** _(if A wins)_:
- WS7 P / I / D = 1 / 0 / 0
- Sensitivity = ___
- Polarity = ___
- Bounds = ±___ V
- `FASTPIEZO:CONTROLPROPORTIONAL` = ___
- `FASTPIEZO:CONTROLINTEGRAL` = ___
- `SLOWPIEZO:LOCKPROPORTIONAL` = ___
- `SLOWPIEZO:LOCKLINTEGRAL` = ___

### Production commitment steps (when winner picked)

1. Save winning Matisse Commander config: `Matisse > Configuration > Save`
   as `WS7-{winner}-Production`. Set as default.
2. Save winning WS7 config: HF_Locking GUI "Save PID Config" → backs up
   `pid_config.json`. Commit to git as
   `GUIs/HF_Locking/pid_config_{winner}_production.json`.
3. If A wins: leave front-panel switch on **Extern**. Confirm label readable.
4. Update `docs/matisse-c-external-locking.md` with chosen path
   highlighted as production.
5. Add startup sanity check in HF_Locking that confirms current WS7 mode
   + cable position match expected production config (e.g. for A: refuse
   to engage if `FASTPIEZO:INPUT?` reads exactly 0.0 → broken cable).

---

## Failure modes — when to call for help vs push through

| Symptom | Phase | Diagnosis | Self-fix? |
|---|---|---|---|
| Phase 0 baseline can't hold | 0 | Internal lock broken — Etalon / pump issue | **No, call lab help** |
| Counterdrift "Laser Locked?" never goes green | 1 | Internal ref-cell lock unstable; Counterdrift won't engage. Possibly WS7-disable left in incomplete state | Re-enable WS7 then start fresh |
| `FASTPIEZO:INPUT?` reads 0.0 in Phase 2 sanity check | 2 | Cable disconnected, WS7 not in deviation mode, or polarity reversed at WS7 source | Verify cable + WS7 GUI |
| Phase 2 lock diverges immediately | 2 | Polarity wrong — positive feedback | Flip Polarity in WS7 |
| Phase 2 Fast Piezo rings at kHz | 2 | Gain ≫ stable region — factory ref-cell gains don't apply | Reduce both Fast Piezo gains 10× and restart |
| Mode hops mid-shot, any candidate | any | Step exceeds Piezo Etalon mode — coordinated re-tune needed | Reduce step size below ~5 GHz OR add Candidate G overlay |
| Lock holds but WS7 drifts despite LOCK=TRUE | any | WS7 calibration drift, not laser drift | Recalibrate WS7 (Ne lamp / He-Ne) |

---

## Logs

Create `docs/commissioning-logs/` (if not present) and write each phase's
output there as plain text:
- `2026-MM-DD-phase0-w.txt` — baseline metrics
- `2026-MM-DD-phase1-c.txt` — Counterdrift A/B
- `2026-MM-DD-phase2-a.txt` — DSP External Input bypass
- `2026-MM-DD-phase3-g.txt` — GoTo overlay (if attempted)
- `2026-MM-DD-phase4-decision.md` — final decision + production gains table

Commit at the end of each phase. These are scientific records — version
them.
