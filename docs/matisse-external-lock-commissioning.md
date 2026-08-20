# Matisse C-S External Lock — Parallel Investigation Runbook

Phased lab procedure to test multiple lock architectures against the same
shot pattern + failure metrics, pick the empirical winner. See
[matisse-c-external-locking.md](matisse-c-external-locking.md) for the
architecture details, ruled-out paths, and the corrected failure
mechanism (§7 of that doc).

**Rewritten 2026-05-23** to reflect findings from inspecting the local
Matisse Commander install: Counterdrift has no documented remote API
(per-shot scanning requires custom LabVIEW plug-in), the Network DLL is
not shipped pre-built (must be compiled from source), and LocalGoTo
exists as a separate plug-in optimized for in-mode hops.

**Channel note (2026-07-29):** TiSa_1 moved WS7 ch4 → ch1 (crosstalk —
see `wavemeter-channel-move.md`). Channel references below are updated;
logs/photos taken before that date show ch4.

## Candidates

| Tag | Architecture | Cable | Internal ref-cell lock | Per-shot capable? |
|---|---|---|---|---|
| **W** | Current WS7-direct PID (baseline) | Rear item 13 | ON | Yes |
| **C-static** | Counterdrift plug-in in set-and-hold mode | Rear item 13 (cable becomes dead weight) | ON | **No** — static target only |
| **C-perShot** | Counterdrift + custom plug-in for remote setpoint | same | ON | Yes (but requires LV work) |
| **A** | DSP External Input bypass | Front item 4 (cable moved) + switch Extern | OFF | Yes |
| **G** | GoTo via Sirah Network DLL or custom plug-in | (no cable change) | ON | Yes (slow, ~1–3 sec/shot) |
| **L** | LocalGoTo via custom plug-in | (no cable change) | ON | Yes (fast, ~100–500 ms/shot) |

## Acceptance test (run identically for all per-shot candidates)

**Test shot pattern:** 100 shots, BLACS sequence, sub-MHz step
resolution, 5–10 MHz hops in arbitrary order within a ~500 MHz envelope
around the production setpoint for TiSa_1 (ch1, ~348.666 THz).

**Metrics captured per run** (write to
`docs/commissioning-logs/2026-MM-DD-phaseN-{w,cs,cp,a,g,l}.txt`):

| Metric | How measured | Threshold to "win" |
|---|---|---|
| Lock-loss count | `FASTPIEZO:LOCK?` FALSE transitions during shots | ≤ 1 per 100 |
| σ at fixed setpoint (10-min hold) | Std-dev of WS7 reading | ≤ 1 MHz |
| Settling time per step | Setpoint write → WS7 within 1 MHz of target | varies by candidate |
| Mode-hop events | WS7 reading jumps > 100 MHz from target | 0 per 100 |
| Slow Piezo search invocations | Transitions to `FREESPEED` mode | 0 per 100 |
| Max σ during scan | Std-dev of WS7 reading around moving target | ≤ 5 MHz |
| Operator-actionable cost | Subjective recovery effort | Whatever's least painful |
| Per-shot latency | Settling time | per acceptance target |

Winner = best Pareto frontier across metrics, not single-axis max.

## Pre-checks (record once before Phase 0; needed for all phases)

| Item | Command / location | Recorded |
|---|---|---|
| Matisse firmware | `*IDN?` via Matisse Commander | ≥ 1.4 (we have 1.20) |
| Matisse Commander version | About dialog | 1.27.0.0 per Changelog |
| Matisse Commander install path | `Get-ChildItem 'C:\Program Files (x86)\Sirah*'` | Sirah-1 and Sirah-2 both present |
| WS7 calibration date | WS7 GUI status bar | within last 24 h |
| Current Fast Piezo gains | `FPZT:CNTRPROP?` `FPZT:CNTRINT?` | factory ref-cell values |
| Current Slow Piezo gains | `SPZT:LPROP?` `SPZT:LINT?` `SPZT:FREESPEED?` | factory ref-cell values |
| Current WS7 PID config (ch1) | `pid_config.json` in `GUIs/HF_Locking/` | P=0.16, I=0.84, D=0.034, Polarity=-1, SensitivityDim=-2 |
| Current TiSa_1 setpoint | WS7 ch1 `cmiPIDCourse` | ~348.666 THz |
| Front-panel DSP switch (item 3) | Visual | **Intern** (expected) |
| Cable destination | Visual trace | Rear item 13 (Reference Cell external) |
| BiFi calibration valid? | `Plug-ins > Wavemeter > Birefringent Filter Calibration` table loaded | Yes / No (REQUIRED for G, recommended for L) |
| Control Scan Measurement done? | `Scan > Control Scan Measurement` last-run date | Yes / No (REQUIRED for G) |
| LabVIEW 2020 32-bit license available? | Lab IT check | Required for Paths C-perShot, G.1, G.2, L |
| Network Server enabled in Matisse Commander? | `Matisse Commander.ini`: `server.tcp.enabled` | Verify (required for G.1, G.3) |

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
5. Verify HF_Locking GUI's external WS7 servo is engaged for ch1.
6. Hold for 10 min, log:
   - `FASTPIEZO:LOCK?` per second
   - `FASTPIEZO:NOW?` (tweeter) per second
   - `SLOWPIEZO:NOW?` per second
   - WS7 ch1 reading per ~200 ms
   - WS7 ch1 DAC voltage per ~200 ms

### Acceptance criteria for Phase 0

- [ ] At baseline (no scan), `FASTPIEZO:LOCK?` stays TRUE for full 10-min hold
- [ ] σ of WS7 reading at fixed setpoint ≤ 5 MHz (loose floor)

If baseline fails → diagnose Piezo Etalon and ref-cell health before
proceeding.

### Run the 100-shot scan test

7. Run the standard 100-shot BLACS sequence over the 500 MHz envelope
8. Capture all metrics from the acceptance table
9. Save log to `docs/commissioning-logs/2026-MM-DD-phase0-w.txt`

### Output

Phase-0 metric values for Candidate W. Numbers every other candidate
must beat.

### Rollback

None — this is the current production setup.

---

## Phase 1 — Counterdrift in set-and-hold (Candidate C-static) — drift baseline

**Goal:** measure long-term drift compensation only. Counterdrift cannot
be driven per-shot by BLACS (no Sirah API), so this phase tests
static-target performance only.

Same session as Phase 0 — no hardware changes.

### Switch from W to C-static

1. Disable WS7 PID for ch1:
   - HF_Locking GUI: external lock toggle OFF for ch1
   - OR direct DLL: `SetDeviationMode(0)` on port 1
2. In Matisse Commander, enable plug-ins (`Matisse > Plug-ins`):
   - **WM Selector** (data layer; or HighFinesse for legacy)
   - **Wavemeter** (umbrella, contains Counterdrift)
3. `Plug-ins > WM Selector > Show Settings`:
   - `Switch` = TRUE, `Channel` = 1
   - `Synched Readout?` = ON (required for 8-channel switched WS7)
   - `Catch errors?` = OFF, `Check Values?` = ON
4. Open `Plug-ins > Wavemeter > Counterdrift` dialog
5. Configure:
   - Unit: THz
   - Setpoint: write TiSa_1 production target (~348.666 THz)
   - PID: **P=0, I=−0.5, D=0, Average=10**
   - Update Time: **300 ms**
   - `Synchronous Wavemeter Readout?` = ON
   - **`AutoReset` = OFF** (its docs warn 100s-of-MHz-to-GHz jumps on C-S)
6. Click `Set to current position` (zeros the initial error)
7. Verify `Main > Lock` is ON (Counterdrift's "Laser Locked?"
   interlock requires it)
8. Click `Activate`

### Sanity check

- [ ] Counterdrift "Laser Locked?" indicator green within 5 s
- [ ] "Control Output" trace stays bounded
- [ ] WS7 reading stays within ±5 MHz of setpoint for 60 s

### Static-hold acceptance

Run 30-min static hold (no BLACS scan, no setpoint changes), log:
- `FASTPIEZO:LOCK?` per second
- WS7 reading per 200 ms
- Counterdrift "Control Output" voltage per 200 ms

- [ ] σ of WS7 reading over 30 min ≤ 1 MHz
- [ ] No lock-loss events
- [ ] Counterdrift Control Output stays within bounds (no rail)

### Per-shot test: SKIP

**Counterdrift has no documented remote setpoint API.** Per-shot BLACS
scanning via Counterdrift is **out of scope for this phase**. To attempt
it, see Phase 1B (C-perShot) which requires LabVIEW development first.

### Interpretation

- **If C-static significantly outperforms W on drift (σ ≤ 1 MHz vs W's
  measured drift):** Counterdrift's safety features (AutoReset/interlock)
  matter; consider C-perShot custom-plug-in development as a future
  project.
- **If C-static ≈ W on drift:** Architecture is the limit. Skip the
  C-perShot LabVIEW work; focus on Candidate A or L.

### Rollback to W

1. `Deactivate` on Counterdrift
2. Re-enable WS7 PID for ch1: `SetDeviationMode(1)` on port 1
3. Verify W operational

---

## Phase 1B — Counterdrift with custom plug-in (Candidate C-perShot)

**Optional, only worth pursuing if Phase 1 C-static shows promising
drift compensation AND the lab has LabVIEW 2020 32-bit license.**

Out of scope for the initial commissioning round. Requires:
- LabVIEW 2020 32-bit license
- ~1 week of LabVIEW work to build a custom MCP_* plug-in that opens a
  TCP listener and uses in-process VI Server to write to the Counterdrift
  dialog's Setpoint control
- Reverse-engineering the VI hierarchy in `MCP Wavemeter.llb` (Sirah
  doesn't publish this — needs LabVIEW IDE inspection)
- Ongoing maintenance burden when Matisse Commander updates rename VIs

If pursued, this plug-in would replace HF_Locking's `SetPIDCourseNum`
write with a TCP call to the custom plug-in's listener. See
[matisse-c-external-locking.md](matisse-c-external-locking.md) §1 for
the architectural sketch.

**Defer this until Phases 2, 3, L are complete and we know whether any
of them is sufficient.**

---

## Phase 2 — DSP External Input bypass (Candidate A)

**Goal:** test whether eliminating the internal ref-cell lock removes
the failure mode entirely. Separate session — needs hardware work.

### Hardware preparation

1. Power off Matisse pump laser **only**. Leave Matisse C control box on
   for DSP voltage monitoring.
2. **Move the WS7 ch1 SMA cable** from rear-panel **Reference Cell
   external input (item 13)** to **front-panel DSP External Input SMA
   (item 4)**.
3. **Do not flip the Intern/Extern switch yet.** Leave on Intern.
4. Apply physical label near item 3: **"EXTERN = WS7 deviation. Verify
   cable + signal before engaging FPZT lock."**

### WS7 deviation-mode configuration

Edit `pid_config.json` for ch1:

```
P = 1.0
I = 0.0
D = 0.0
Average = 10
SensitivityDim = -2  (kept from current — scale ±500 MHz to ±2 V)
SensitivityFactor = 1.0
Polarity = -1  (keep current; flip to +1 if lock diverges)
BoundsMin = -4000.0
BoundsMax = +4000.0
```

Reload via HF_Locking GUI's Restore PID Config dialog
(read-before-write per the `pid-persistence` agent).

### Sanity check the error signal

1. Front-panel switch on **Intern**. WS7 DAC voltage now present at item
   4 but not selected.
2. With internal lock active, briefly flip switch to **Extern**:
   - Query `FASTPIEZO:INPUT?` — should read normalized value within ±1
   - Flip switch back to **Intern**
3. If `FASTPIEZO:INPUT?` reads exactly 0.0 or out-of-range, fix cable
   or WS7 config before proceeding.

### Engage external lock

1. `Main > Lock` OFF in Matisse Commander
2. Set initial Matisse Fast Piezo gains low (~10× below factory):
   - `FASTPIEZO:CONTROLPROPORTIONAL` ← (factory) / 10
   - `FASTPIEZO:CONTROLINTEGRAL` ← (factory) / 10
3. Set initial Slow Piezo gains low (~10× below factory)
4. `FASTPIEZO:CONTROLSETPOINT 0.0` (lock at DSP input = 0 V = WS7 at reference)
5. `FASTPIEZO:LOCKPOINT 0.0`
6. Flip front-panel switch (item 3) to **Extern**
7. `FASTPIEZO:CONTROLSTATUS RUN`
8. Watch Fast Piezo + Slow Piezo waveforms

### Possible immediate outcomes

| Symptom | Cause | Action |
|---|---|---|
| Fast Piezo immediately rails 0 or 1 | Polarity wrong | STOP, flip Polarity, RUN again |
| Fast Piezo oscillates rapidly | Gains too high | Reduce P+I by another 2× |
| Lock acquires but WS7 drifts | Sensitivity wrong / Slow Piezo not following | Tune Slow Piezo up, or rescale sensitivity |
| Lock acquires steady | Continue to acceptance test | |

### Acceptance criteria

- [ ] `FASTPIEZO:LOCK?` TRUE for ≥ 10 min
- [ ] `FASTPIEZO:NOW?` between 0.2 and 0.8 (no rail)
- [ ] σ of WS7 reading ≤ 1 MHz around target

### Tuning recipe (if acceptance fails)

One parameter at a time:

1. **~Hz slow oscillation:** Slow Piezo I too high — reduce by 30%
2. **~tens-of-Hz fast oscillation:** Fast Piezo P too high — reduce by 30%
3. **Drifts to rails:** Slow Piezo not catching up — increase Slow Piezo gains
4. **WS7 noisy below detector resolution:** WS7 sensitivity too high — back off
5. **`LOCK?` flickers FALSE:** tweeter near 95% — adjust mechanical or change setpoint

Document each iteration in commissioning log.

### Per-shot scan test

1. Call `SetDeviationReference(target + Δ)` from BLACS, Δ = +50, +200, +500 MHz
2. Confirm `FASTPIEZO:LOCK?` stays TRUE across each step
3. Run the full 100-shot BLACS sequence
4. Capture metrics
5. Save log to `docs/commissioning-logs/2026-MM-DD-phase2-a.txt`

### Rollback to W

1. `FASTPIEZO:CONTROLSTATUS STOP`
2. Restore Fast Piezo + Slow Piezo gains to factory ref-cell values
3. Flip front-panel switch to **Intern**
4. `Main > Lock` ON in Matisse Commander
5. Re-enable WS7 PID with original config
6. Move SMA cable back from item 4 to item 13
7. Verify W operational

---

## Phase 3 — GoTo plug-in via Network DLL (Candidate G)

**Goal:** test whether per-shot coordinated re-tuning (BiFi + etalons +
piezos) for each setpoint hop avoids the W failure mode by **actively
re-tuning instead of relying on a continuous PID**.

### Prerequisites (one-time setup)

1. **Birefringent Filter Calibration** — run
   `Plug-ins > Wavemeter > Birefringent Filter Calibration`. Takes
   ~minutes. Saves to Matisse Commander config. Must be valid for
   GoTo to work.
2. **Control Scan Measurement** — run
   `Scan > Control Scan Measurement`. Takes ~1 minute. Measures
   MHz/scan-unit conversion factor for the Scan Device (Ref Cell piezo
   on C-S by default).
3. **Network Server enabled** — open
   `C:\Program Files (x86)\Sirah-1\Matisse Commander\Matisse Commander.ini`,
   verify section enabling the Network Server. Default port 30000.
4. **GoTo Options tuned** — `Plug-ins > Wavemeter > GoTo Position &
   Extended Scan Options`:
   - `Precision [GHz]`: **0.001** (1 MHz, for sub-MHz scans)
   - `Scan velocity for reset [1/s]`: 0.01 default (tune later)
   - `Max retries after error`: 2
   - `Delay after locking [ms]`: lower than default 2000 for C-S
     (try 500)
   - `Abort scan on jump detection`: ON
   - `Enable Control Scan`: ON

### Path G.1 — Sirah Network DLL (requires LabVIEW 2020 32-bit license)

**⚠ The pre-built `MatisseDLLExample.dll` is NOT shipped.** The Addon
zip `C:\Program Files (x86)\Sirah-1\Matisse Commander\Addons\
LabVIEW - Matisse Commander.zip` contains only the LabVIEW source
(`ExampleProject.lvproj` + `.vi` files) and Python wrappers.

**Build step (one-time):**

1. Extract the Addon zip to a working folder
2. Open `Examples/ExampleDLL/ExampleProject.lvproj` in LabVIEW 2020
   32-bit
3. Build → produces `build/MatisseDLLExample.dll`
4. Copy DLL + all dependencies (`Dependent/Wavemeter/`, `Dependent/`
   packed libraries) to a deployment folder co-located with the BLACS
   Python integration code

**BLACS-side Python integration** (sketch):

```python
# In a new BLACS device module or extension of LaserLockDevice
import ctypes

class MatisseGoToDLL:
    def __init__(self, dll_path, mc_ip='127.0.0.1', mc_port=30000):
        # NOTE: Python must be 32-bit to load this DLL
        self._dll = ctypes.CDLL(dll_path)
        self._dll.GoToPosition_Network.argtypes = [
            ctypes.c_double,   # GotoPositionGHz
            ctypes.c_char_p,   # NetworkAddress
            ctypes.c_long,     # Port
        ]
        self._ip = ctypes.create_string_buffer(mc_ip.encode('utf-8'))
        self._port = mc_port

    def goto_GHz(self, freq_ghz):
        rc = self._dll.GoToPosition_Network(
            ctypes.c_double(freq_ghz),
            self._ip,
            ctypes.c_long(self._port),
        )
        return rc  # 0 = OK
```

Per-shot path in BLACS `transition_to_buffered`:

```python
target_ghz = float(setpoint_thz * 1000)  # THz → GHz
rc = matisse.goto_GHz(target_ghz)
if rc != 0:
    raise RuntimeError(f"GoTo failed, exit_code={rc}")
```

### Path G.2 — Custom MCP_* plug-in (also requires LV 2020 license, no DLL)

Instead of building the example DLL, write a custom plug-in that opens
a TCP listener and internally calls
`MCP WM Goto Wavemeter Position Wait or Stop.vi` (documented Ch. 5).
Skips the Network Server hop. ~3 days LV work.

### Path G.3 — Pure-Python Network Server client (NO LV license needed)

Re-implement GoTo's algorithm in Python, talking directly to the
Matisse Commander Network Server (TCP port 30000, VISA text protocol).
Programmer's Guide Ch. 3 points at `nelsond/sirah-matisse-commander`
GitHub repo as a starting reference.

Pros: no LabVIEW required, fully accessible from any Python.
Cons: reproduces ~1000 lines of LabVIEW GoTo algorithm in Python.
Significant work, ~2 weeks.

### Sanity check (any path)

1. Operator manually calls GoTo on a target ~10 MHz away from current
   frequency. Confirm laser actually reaches target within `Precision`.
2. Time the GoTo call (start time, completion time). Record per-call
   latency for in-mode hop.
3. Verify `FASTPIEZO:LOCK?` is TRUE after GoTo completes.

### Per-shot scan test (Path G)

1. Configure BLACS sequence with arbitrary-order 5–10 MHz setpoint hops
2. Each setpoint hop calls `goto_GHz(target)` synchronously, blocks
   until completion
3. Shot rate WILL be capped by GoTo latency (~1–3 sec/shot expected for
   in-mode hops) — verify experiment can accept this
4. Run 100-shot sequence, capture metrics
5. Save log to `docs/commissioning-logs/2026-MM-DD-phase3-g.txt`

### Rollback to W

1. Stop using GoTo per shot in BLACS sequence
2. Re-enable WS7 PID + HF_Locking external lock
3. Verify W operational

---

## Phase L — LocalGoTo plug-in (Candidate L)

**Goal:** test the lower-latency in-mode GoTo variant. Bridge between W
(fast but fragile) and G (slow but robust).

### Path L availability

`MCP LocalGoTo Plug-In.llb` ships with Matisse Commander and is enabled
via `Matisse > Plug-ins`. **But** its VIs (notably
`MCP LocalGoTo Set Laser To.vi`) are NOT in Chapter 5's public list.
External invocation requires the same custom-plug-in path as
Path C-perShot or G.2.

### Prerequisites

1. **LocalGoTo Calibration** — `MCP LocalGoTo Calibrate.vi` builds a
   ref-cell-position-to-frequency table. Distinct from BiFi Calibration
   + Control Scan Measurement. Done once per laser config.
2. Same as Phase 3 (Matisse Commander running, internal lock active,
   etc.).

### Implementation

**Custom MCP_* plug-in (~1 week LV work, LabVIEW 2020 32-bit license required):**

The plug-in:
1. Opens a TCP listener (e.g. port 30001 to avoid Network Server's 30000)
2. Accepts text commands like `SETF 348.666410\n` (target in THz)
3. Internally calls `MCP LocalGoTo Set Laser To.vi` with the target
4. Reports completion + exit code back over TCP

**BLACS-side Python integration** (sketch):

```python
import socket

class MatisseLocalGoTo:
    def __init__(self, host='127.0.0.1', port=30001, timeout_s=2.0):
        self._host, self._port = host, port
        self._timeout = timeout_s

    def goto_THz(self, freq_thz):
        with socket.create_connection((self._host, self._port),
                                       timeout=self._timeout) as s:
            s.sendall(f"SETF {freq_thz:.7f}\n".encode('ascii'))
            resp = s.recv(1024).decode('ascii').strip()
            # Expect: "OK" or "ERR <code>"
            if not resp.startswith("OK"):
                raise RuntimeError(f"LocalGoTo failed: {resp}")
```

### Sanity check

1. Operator clicks LocalGoTo menu item in Matisse Commander, sets
   target ~10 MHz away. Verify laser arrives within ~500 ms.
2. Once the custom plug-in is built: send `SETF` over TCP, time the
   response, verify laser at target.

### Per-shot scan test (Path L)

Same as Phase 3 but with the LocalGoTo TCP call instead of GoTo's DLL
call. Expect faster per-shot latency (~100–500 ms vs ~1–3 sec).

Save log to `docs/commissioning-logs/2026-MM-DD-phaseL-l.txt`.

### Rollback

1. Stop using LocalGoTo per shot in BLACS sequence
2. Disable LocalGoTo plug-in if it interferes (Matisse > Plug-ins
   uncheck)
3. Re-enable WS7 PID + HF_Locking external lock
4. Verify W operational

---

## Phase 4 — Decision and commit

After Phases 0, 1, 2, 3, L complete (or whichever subset was attempted):

| Metric | W | C-static | A | G | L | Winner |
|---|---|---|---|---|---|---|
| Lock-loss / 100 | _ | (no scan) | _ | _ | _ | |
| σ at fixed (MHz) | _ | _ | _ | _ | _ | |
| Settling (ms) | _ | (n/a) | _ | _ | _ | |
| Mode-hops / 100 | _ | (no scan) | _ | _ | _ | |
| Search invocations / 100 | _ | (no scan) | _ | _ | _ | |
| Max σ scan (MHz) | _ | (n/a) | _ | _ | _ | |
| Per-shot latency | _ | (n/a) | _ | _ | _ | |
| Operator cost | _ | _ | _ | _ | _ | |

Pick the winner. Document in
`docs/commissioning-logs/2026-MM-DD-phase4-decision.md`.

### Production gains tables (fill in after winner selected)

**Candidate W production config** _(if W wins — keep current)_:
- WS7 P / I / D = ___ / ___ / ___
- Sensitivity = ___
- Polarity = ___
- Bounds = ___ / ___

**Candidate A production config** _(if A wins)_:
- WS7 P / I / D = 1 / 0 / 0
- Sensitivity = ___
- Polarity = ___
- Bounds = ±___ V
- `FASTPIEZO:CONTROLPROPORTIONAL` = ___
- `FASTPIEZO:CONTROLINTEGRAL` = ___
- `SLOWPIEZO:LOCKPROPORTIONAL` = ___
- `SLOWPIEZO:LOCKLINTEGRAL` = ___

**Candidate G production config** _(if G wins)_:
- Matisse Commander Network Server port = ___
- DLL build location = ___
- `Precision [GHz]` = ___
- `Scan velocity for reset [1/s]` = ___
- BLACS goto_GHz timeout = ___ s

**Candidate L production config** _(if L wins)_:
- Custom plug-in TCP port = ___
- LocalGoTo calibration date = ___
- BLACS goto_THz timeout = ___ s

### Production commitment steps (after winner picked)

1. Save winning Matisse Commander config:
   `Matisse > Configuration > Save` as `WS7-{winner}-Production`. Set
   as default.
2. Save winning WS7 config: HF_Locking "Save PID Config" → commit
   `pid_config.json` as
   `GUIs/HF_Locking/pid_config_{winner}_production.json`.
3. If A wins: leave front-panel switch on **Extern**, confirm label readable.
4. If G or L wins: ensure DLL/plug-in is in a known location with
   versioned filename, document the build steps.
5. Add startup sanity check in HF_Locking that confirms current
   architecture matches expected production config.
6. Update `docs/matisse-c-external-locking.md` with chosen path
   highlighted as production.

---

## Failure modes — when to call for help vs push through

| Symptom | Phase | Diagnosis | Self-fix? |
|---|---|---|---|
| Phase 0 baseline can't hold | 0 | Internal lock broken — Etalon / pump issue | **No, call lab help** |
| Counterdrift "Laser Locked?" never goes green | 1 | Internal ref-cell lock unstable; possibly WS7-disable left incomplete | Re-enable WS7 then start fresh |
| Phase 2 `FASTPIEZO:INPUT?` reads 0.0 | 2 | Cable disconnected, WS7 not in deviation mode, or polarity reversed at WS7 | Verify cable + WS7 GUI |
| Phase 2 lock diverges immediately | 2 | Polarity wrong — positive feedback | Flip Polarity in WS7 |
| Phase 2 Fast Piezo rings at kHz | 2 | Gain ≫ stable region — factory ref-cell gains don't apply | Reduce both gains 10× and restart |
| Phase 3 `GoToPosition_Network` returns non-zero exit code | 3 | Network Server not enabled, wrong port, DLL build mismatch, BiFi/Control-Scan calibration missing | Verify each prerequisite from "Prerequisites (one-time setup)" |
| Phase 3 GoTo overshoots target by > Precision | 3 | `Precision [GHz]` too loose, or `Scan velocity for reset` too high | Lower Precision, slow Scan velocity |
| Mode hops mid-shot, any candidate | any | Step exceeds Piezo Etalon mode (~18 GHz) — only G + L handle this | Reduce step size below ~5 GHz, OR pick G/L |
| Lock holds but WS7 drifts despite LOCK=TRUE | any | WS7 calibration drift, not laser drift | Recalibrate WS7 (Ne lamp / He-Ne) |

---

## Logs

Create `docs/commissioning-logs/` (if not present) and write each
phase's output there as plain text:
- `2026-MM-DD-phase0-w.txt` — baseline metrics
- `2026-MM-DD-phase1-cs.txt` — Counterdrift set-and-hold drift
- `2026-MM-DD-phase2-a.txt` — DSP External Input bypass
- `2026-MM-DD-phase3-g.txt` — GoTo via Network DLL
- `2026-MM-DD-phaseL-l.txt` — LocalGoTo via custom plug-in (if attempted)
- `2026-MM-DD-phase4-decision.md` — final decision + production gains

Commit at the end of each phase. These are scientific records — version
them.
