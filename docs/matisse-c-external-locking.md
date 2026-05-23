# Matisse C-S External Locking — Candidate Architectures

Reference for the laser-lock architectures available on a **Matisse C-S** +
HighFinesse **WS7 NeLAC** with an 8-channel fiber switcher.

**This doc was rewritten 2026-05-22 after operator interrogation revealed
the actual failure mechanism of the previous architecture and the previous
"choose one of two paths" framing was misleading.** Earlier versions of this
doc treated DSP External Input + External PID plug-in as the only options —
that framing was wrong. See §6 below for the corrected mechanism.

Sources:
- `Matisse C Manual v1.2.3` (USB stick, `Sirah USB\Matisse Commander\Manuals\`)
- `Matisse Programmer's Guide v2.4.1` (same dir)
- `Manual WS7 NeLAC` (`GUIs/HF_Locking/Manual WS7 NeLAC (1).pdf`)
- Matisse Commander Plug-ins help (`Sirah Control.CHM` → `Plug-ins` topic tree)

## Lab-confirmed operating context

| | |
|---|---|
| Laser | Matisse C-S (side-of-fringe ref cell, no PDH / no EOM) |
| Primary use | Scanning high-power tunable Ti:Sa — spectroscopy + cooling + imaging + repump |
| Stability budget | ~1 MHz, seconds-to-minutes (current achievable WS7-limited floor) |
| Per-shot scan | Sub-MHz step resolution, 5–10 MHz steps within ~500 MHz envelope, **arbitrary frequency order** (not just ramps) |
| Wavemeter | HighFinesse WS7 NeLAC, 8-channel fiber switcher, ~5 Hz/channel, ~40 Hz aggregate |
| Wavemeter lock | WS7 built-in 8-channel PID DAC card, configured via HF_Locking GUI (`GUIs/HF_Locking/`) over `wlmData.dll` |

## Matisse C-S piezo / scan-piezo hierarchy

| Actuator | Bandwidth | Role | Scan Piezo? |
|---|---|---|---|
| Fast Piezo (tweeter) | kHz-ish | Cavity mirror; chases ref-cell flank in internal lock | No |
| Slow Piezo (tuning mirror, "woofer") | ~Hz | Long-stroke cavity mirror; offloads Fast Piezo | Selectable |
| Reference cell piezo | ~Hz | Moves ref-cell mode comb → shifts lock point | **Selectable (default on C-S)** |

"Scan Piezo" is a logical name. `Scan > Scan Device Configuration` (Matisse
Commander) picks which physical piezo it points to. On a Matisse R it's the
Slow Piezo; on a stabilized Matisse C-S it can be either the Ref Cell Piezo
(default) or the Slow Piezo.

## 0 — Baseline architecture (Candidate W): current WS7-direct PID

What's running in the lab today.

```
WS7 (8-ch fiber switch, ~5 Hz/ch) ── wlmData.dll
       │ in HF_Locking WavemeterWorker thread
       ▼
WS7 built-in 8-channel PID DAC card (Sirah-supplied)
   ch4 config: P=0.16, I=0.84, D=0.034, T=0.02, dt=0.01, UseTa=1,
               Polarity=-1, SensitivityDim=-2, Bounds 0..9000 mV
       │
       ▼ DAC voltage on ch4 (~0..5 V in practice)
       │ rear-panel SMA cable
       ▼ Matisse C Reference Cell external input (item 13)
       │
       ▼ ref-cell piezo moves → ref-cell mode comb shifts → flank position moves
       │
       ▼ Internal Matisse ref-cell lock (must chase the moving flank):
            Fast Piezo PID (kHz) + Slow Piezo offload (Hz)
       │
       ▼ Laser frequency ── back into WS7 → loop closes
```

HF_Locking GUI is the **monitor + comms layer** — it configures the WS7 PID
via DLL, reads back state, broadcasts WS7 readings to BLACS over ZMQ, and
exposes setpoints + lock indicators in BLACS via `LaserLockDevice`. It does
NOT run its own PID loop.

This is structurally equivalent to the Matisse Commander
`Plug-ins > Wavemeter > Counterdrift` architecture, just implemented with
the WS7's own PID instead of Sirah's plug-in.

### Why it's painful in practice

See §6 for the mechanism. Symptom: arbitrary-order setpoint hops break the
internal ref-cell lock. Slow Piezo enters its `FREESPEED` search mode and
sweeps in frequency until either it re-acquires (possibly on the wrong
mode) or the operator disables.

## 1 — Candidate C: Counterdrift plug-in (Matisse Commander)

**Same cable, same actuator path (ref-cell piezo).** Replace WS7's
built-in PID with Sirah's Counterdrift plug-in in Matisse Commander.

### Differences from W

| | Candidate W (current) | Candidate C (Counterdrift) |
|---|---|---|
| PID implementation | WS7-internal | Matisse Commander plug-in |
| Process value source | WS7 reading direct | Via Matisse Commander WM Selector / HighFinesse plug-in |
| Soft-start on engagement | None | `Set to current position` button (sets setpoint to current laser freq before activating) |
| Rail recovery | `ClearHistoryOnRangeExceed` (clears integral, no recenter) | `AutoReset` (recenters Scan Device on rail) — **but doc warns this causes 100s-of-MHz-to-GHz jumps on C-S** |
| Interlock | None | `Laser Locked?` indicator gates loop — refuses to run unless internal ref-cell lock holds |
| Fresh-data handling | Cached `GetFrequencyNum` from HF_Locking | `Synchronous Wavemeter Readout?` toggle (blocks until fresh data when ON) |
| BLACS scan path | `SetPIDCourseNum` step writes | Counterdrift `Setpoint` writes via VI Server / SCPI |

### Configuration

Per the Counterdrift docs:
- Front-panel cable: unchanged (WS7 ch4 still to rear-panel item 13)
- Disable WS7 PID for ch4 via DLL (`SetDeviationMode(0)` per port)
- Enable WM Selector or HighFinesse plug-in (data layer) in Matisse Commander
- Open `Plug-ins > Wavemeter > Counterdrift` dialog
- Sirah-suggested start: **P=0, I=−0.5, D=0, Average=10, Update=300 ms**
- `Synchronous Wavemeter Readout?` = **ON** (required for 8-channel switched WS7)
- `AutoReset` = **OFF** initially (observe rail behavior; AutoReset can cause GHz jumps)
- Scan Device target: ref cell piezo (default for C-S via `Scan > Scan Device Configuration`)
- Internal Matisse `Main > Lock`: **stays ON** (Counterdrift requires it)

### Hypothesis (untested)

Same architecture as W → likely same failure mode on arbitrary-order step
changes (ref-cell lock breaks → Slow Piezo search). Counterdrift's safety
features (`Set to current position` soft-start, AutoReset, Laser-Locked
interlock) may reduce or rearrange the symptoms but don't change the
underlying fragility.

Worth a 30-minute A/B test against W to confirm or refute.

## 2 — Candidate A: DSP External Input bypass

**Removes the internal ref-cell lock entirely.** WS7 deviation voltage
feeds the Matisse Fast Piezo PID directly via the front-panel DSP
External Input SMA.

```
WS7 ── ch4 DAC (deviation mode: P=1, I=D=0) ────► Front-panel DSP External Input SMA (item 4)
                                                          │ Intern/Extern switch (item 3) = Extern
                                                          ▼
                                                 Matisse Fast Piezo PID
                                                 (uses DSP-input voltage as error signal)
                                                          │ (Slow Piezo offload behind it)
                                                          ▼
                                                 Laser frequency
```

### Differences from W

| | Candidate W | Candidate A (DSP bypass) |
|---|---|---|
| Cable termination | Rear-panel item 13 (Reference Cell external) | Front-panel item 4 (DSP External Input) |
| Front-panel switch (item 3) | Intern | **Extern** |
| Internal ref-cell lock | ON | **OFF** (`Main > Lock` disabled) |
| WS7 PID mode | Full PID (P=0.16, I=0.84) | **Deviation-only** (P=1, I=0, D=0) |
| Actuator driven | Ref cell piezo | Fast Piezo (via Matisse FAST PIEZO PID) |
| Closed loops | 2 (WS7 PID + internal ref-cell lock) | **1** (WS7 deviation → Matisse Fast Piezo PID) |
| Matisse Fast Piezo PID gains | Factory ref-cell values | **Must be re-tuned from scratch** (factory assumes ref-cell photodiode signal, not WS7 deviation voltage) |

### Configuration

**Hardware:**
- Move SMA cable: rear-panel item 13 → front-panel item 4
- Flip front-panel switch (item 3) to **Extern**
- Physical label near switch: "Extern = WS7 deviation. Verify signal before engaging."

**WS7 (deviation mode):**
- Disable PID-mode for ch4 (or set P=1, I=0, D=0 explicitly via DLL —
  HF_Locking's `config.py` registries already cover all the relevant
  cmiPID_* / cmiDeviation* constants, so this is a config-file edit not
  a code change)
- Sensitivity: scale so ±500 MHz fits inside ±4 V (safely inside Matisse
  ±5 V DSP range)
- Bounds: clip at ±4 V (`BoundsMin = -4000`, `BoundsMax = 4000`)
- Polarity: determined empirically on first lock (flip if diverges)
- Channel: same as today

**Matisse C:**
- `Main > Lock` OFF (disable internal ref-cell lock)
- Initial `FASTPIEZO:CONTROLPROPORTIONAL`, `:CONTROLINTEGRAL` — start
  at ~10× below factory ref-cell values; ramp up while watching
  `FASTPIEZO:NOW?` for ringing
- Initial `SLOWPIEZO:LOCKPROPORTIONAL`, `:LOCKLINTEGRAL` — same, start low
- `FASTPIEZO:CONTROLSETPOINT 0.0` (lock at DSP input = 0 V = WS7 at setpoint)

### Per-shot scan path

BLACS sets the WS7 **reference** (not the setpoint) via
`SetDeviationReference`. The Fast Piezo PID then chases the new error-
signal zero automatically. **No setpoint-step transient on the Matisse
side** because nothing changes for the Matisse PID; only what WS7 calls
"zero" moves.

### Hypothesis (untested)

Eliminates the entire failure-mode chain in §6 because there's no
internal ref-cell lock to drop and no Slow Piezo search mode to trigger.
Setpoint changes propagate via Fast Piezo motion (smoothest, highest-BW
actuator on a C-S) rather than via ref-cell mode shift.

### What's lost

Nothing the lab needs:
- The internal ref-cell-to-Fast-Piezo lock was contributing fragility
  (chasing the moving flank) without contributing stability the lab
  cares about — the lab is already WS7-noise-limited at ~1 MHz per the
  operator.
- 3.4 kΩ DSP input impedance is fine for the WS7 PCI DAC's low-Z output.

### Risks

- Polarity wrong on first attempt — expected; flip and retry
- Initial Matisse PID gains too high → ringing → reduce by 2× and retry
- WS7 measurement gaps (channel switching, exposure auto-adjust) freeze
  the DAC at last value → Fast Piezo drifts for 200 ms gaps
- Front-panel Intern/Extern switch is **hardware-only** — not BLACS-
  remotable. Mode is a session-level setting, not per-shot.

## 3 — Candidate G: GoTo plug-in (Matisse Commander) — overlay candidate

`Plug-ins > Wavemeter > GoTo` is **not a lock loop** — it's a coordinated
re-tune: BiFi + Thin Etalon + Piezo Etalon + Slow Piezo + Ref Cell Piezo
all move together to put the laser on a user-defined wavelength.

### Why it might matter for us

- Survives mode hops because it actively searches for the right mode
  during the move (BiFi-driven mode selection + Thin Etalon scan +
  Piezo Etalon mode-find — see Manual ch.9 + Plug-ins doc)
- For arbitrary-order frequency hops **larger than one Piezo Etalon
  mode (~18 GHz FSR)**, no PID-driven scheme alone (W/C/A) can reliably
  switch modes. GoTo coordinates the mode change.
- Per-step is **slow** (~seconds for full BiFi/etalon coordination), so
  it fits only if shot rate ≤ 1 Hz OR if used as a per-shot pre-positioner
  before engaging a fine WS7-driven lock during the shot itself.

### Configuration

- Requires BiFi calibration + Control Scan Measurement done beforehand
  (operator confirms both are in place)
- Doesn't replace the lock — layers on top of W / C / A as a
  pre-positioner
- BLACS-side: would need a new `goto_wavelength(target)` device method
  that calls Matisse Commander VI Server, blocks until GoTo completes,
  then engages the configured fine lock
- Internal ref-cell lock state: ON for W and C overlays, OFF for A

### When to use it

Only if Phase 0-2 results show that W / C / A handle scans within one
Piezo Etalon mode (~18 GHz) but fail on larger hops. For our typical
500 MHz scan envelope, GoTo overlay is probably not needed.

## 4 — Paths NOT being tested (with reasons)

| Path | Why ruled out |
|---|---|
| **External PID plug-in** (Matisse Commander) | Same architecture as Counterdrift (ref-cell-piezo-driven PID on top of internal lock) but requires NI-DAQmx Global Channel + analog process value (e.g. atomic vapor cell + photodiode) we don't currently have. Strictly dominated by Counterdrift for our use case. |
| **Strain Gauge plug-in** | Requires strain gauge physically glued to the piezo. Not installed. |
| **HighFinesse / WM Selector plug-ins** | Data layer only, not lock loops. We already have equivalent functionality via `wlmData.dll` direct from HF_Locking GUI. |
| **PZA plug-in** | Sirah piezo-amplifier card option. Different scan-range hardware. Not a lock architecture. |
| **Picoscrew plug-in** | Beam alignment + wavelength-range switching. Not lock-related. |

## 5 — Comparison matrix (how candidates are scored)

Same shot pattern run against W, C, A, and A+G. Same acceptance metrics.

| Metric | How measured | Threshold to "win" |
|---|---|---|
| Lock-loss events per 100-shot sequence | Count `FASTPIEZO:LOCK?` transitions to FALSE during shots | ≤ 1 per 100 |
| σ at fixed setpoint (10 min hold) | Std-dev of WS7 reading | ≤ 1 MHz |
| Settling time after step setpoint change | `SetPIDCourseNum` / `SetDeviationReference` → WS7 within 1 MHz of target | ≤ 200 ms |
| Mode-hop events per 100 shots | Discrete WS7 reading jumps > 100 MHz from target | 0 per 100 |
| Slow Piezo search-mode invocations | Transitions to `FREESPEED` mode (or equivalent for A) | 0 per 100 |
| Max σ during scan | Std-dev of WS7 reading around moving target | ≤ 5 MHz |
| Operator-actionable cost | Subjective recovery effort after failure | Whatever's least painful |

Picking the winner is a Pareto-front question across these metrics, not
a single-axis maximum.

Expected tradeoffs (predictions only — verify empirically):
- W: low setup cost, high lock-loss rate
- C: low setup cost; likely same lock-loss as W (same architecture)
- A: high setup cost; likely much lower lock-loss
- G overlay: very high per-shot latency, very robust against mode hops

## 6 — Failure mechanism of Candidate W (corrected, operator-confirmed)

This section exists because I (Claude) repeatedly proposed wrong
mechanisms in the planning conversation that led to this doc. The
operator corrected the mechanism on 2026-05-22. Documenting it explicitly
so the next reader doesn't repeat my errors.

**What actually happens when BLACS step-changes a setpoint:**

1. BLACS writes new setpoint to WS7 ch4 via `SetPIDCourseNum`.
2. WS7 PID immediately sees a ~5–10 MHz step error.
3. WS7 PID drives ref-cell DAC voltage toward new equilibrium —
   aggressive even with I=0.84 because integral wind-up was tuned for
   continuous tracking.
4. Ref-cell piezo moves → ref-cell mode comb shifts → flank position moves.
5. **Internal Matisse ref-cell lock breaks** — Fast Piezo tries to compensate
   but rails (`FASTPIEZO:LOCK?` checks tweeter position 5%–95% range,
   per Matisse Programmer's Guide p.68; outside that range `LOCK? = FALSE`).
6. With `FASTPIEZO:LOCK?` FALSE, the Slow Piezo enters `FREESPEED`
   search mode (per Matisse Manual: "in the not-locked case, [Slow Piezo]
   will scan the laser to a resonance of the reference resonator").
7. Slow Piezo sweeps cavity length in one direction looking for a
   ref-cell flank to re-lock to.
8. While the Slow Piezo sweeps, cavity length changes — the Piezo
   Etalon waveform shakes in response. This is a **downstream effect**,
   NOT the cause. Earlier hypotheses pinning the failure on Piezo Etalon
   bandwidth were wrong.
9. The Slow Piezo either finds a ref-cell flank (possibly on the wrong
   mode → laser at wrong frequency) and re-locks, or it doesn't and the
   operator gives up.

**Why the operator's previously-tried fixes don't help:**

| Tried | Why it didn't work |
|---|---|
| Reduced WS7 PID I gain | Scans become too slow; below some threshold the experiment isn't viable |
| Capped `cmiDeviationMaxChangePerShot` | Per-measurement DAC step is capped but multi-cycle integral accumulation still moves the ref-cell piezo enough to break the lock |
| Tuned close in frequency (small steps) | Didn't help — any step large enough to be experimentally useful still breaks the lock |
| Continuous ramps via Matisse Commander `Scan > Scan Setup` | Works mechanically, but the experiment requires arbitrary frequency order, not ramps |

**The architecture itself — internal ref-cell lock as inner loop, driven
by an outer servo on the ref-cell piezo — is the source of fragility**
regardless of whether the outer servo is the WS7's PID (W), Counterdrift
(C), or External PID. To beat this we need an architecture that
eliminates the internal-ref-cell-lock-on-moving-flank dependency.
That's what Candidate A does.

## SCPI command reference (works for W, C, and A)

From the Matisse Programmer's Guide:

| Command | Use |
|---|---|
| `FASTPIEZO:INPUT?` | Read DSP-input voltage normalized to −1..1 (works in Intern or Extern) |
| `FASTPIEZO:CONTROLSETPOINT <f>` | Fast Piezo PID target |
| `FASTPIEZO:LOCKPOINT <f>` | Initial-acquisition target; slewed to CONTROLSETPOINT |
| `FASTPIEZO:CONTROLSTATUS RUN\|STOP` | Engage / disengage Fast Piezo PID |
| `FASTPIEZO:LOCK?` | TRUE iff tweeter sits 5–95 % of range |
| `FASTPIEZO:CONTROLPROPORTIONAL`, `:CONTROLINTEGRAL` | Fast Piezo gains |
| `SLOWPIEZO:LOCKPROPORTIONAL`, `:LOCKLINTEGRAL`, `:FREESPEED` | Slow Piezo gains + search speed |

`FREESPEED` is the Slow Piezo's velocity in search mode — relevant to
Candidate A's tuning (we want it small for our setup since we're not
relying on it to acquire lock anymore).

The **Intern/Extern switch (item 3) is hardware-only.** No SCPI
equivalent. Mode is a session-level commitment for Candidate A.

## DSP External Input electrical spec (Candidate A)

From Matisse C Manual p.145:

| Parameter | Value |
|---|---|
| Connector | SMA jack (MIL-C-39012) |
| Input voltage range | **−5.0 … +5.0 V** |
| Input impedance | **3.4 kΩ** |
| Internal normalization | input/5 V → −1.0 … +1.0 (via `FASTPIEZO:INPUT?`) |

3.4 kΩ is low — WS7's PCI DAC drives it fine. Never insert a high-Z
attenuator or unbuffered source.

## WS7 deviation-mode configuration (Candidate A)

Built-in or PCI DAC:

| Parameter | Built-in WS7 DAC | External PCI DAC |
|---|---|---|
| Output range | ±4.096 V | ±10.0 V |
| Resolution | 0.125 mV (16-bit) | 16-bit |
| Step time (`drive immediately`) | ~200 µs/step | same |
| Connector | LEMO at rear | D-Sub on PCI card |

For Candidate A, configure WS7 with **P=1, I=0, D=0**, sensitivity sized
so ±500 MHz fits inside ±4 V (well within Matisse ±5 V DSP input range).
Bounds at ±4 V. Polarity determined empirically.

WS7 DLL functions (already wrapped in HF_Locking `wlm_utils.py`):
`SetDeviationMode`, `SetDeviationReference`, `SetDeviationSensitivity`,
`GetDeviationSignal[Num]`, `GetAnalogIn`.

WS7 data cadence on this PC: ~5 Hz per channel, ~40 Hz aggregate over 8
channels — see [hf-locking-rates.md](hf-locking-rates.md).

## BLACS integration touchpoints

For all candidates, the WS7 communication path already exists in
`userlib/user_devices/LaserLockDevice/` over ZMQ (REQ-REP port 3796 +
PUB-SUB port 3797). Candidate-specific additions:

- **W (today):** `PROGRAM_VALUE` writes setpoint via `SetPIDCourseNum`
  → WS7 PID chases. No code change needed.
- **C:** `PROGRAM_VALUE` writes Counterdrift setpoint via Matisse
  Commander VI Server. New HF_Locking method
  `set_counterdrift_setpoint(freq)` calling Matisse VI server.
- **A:** `PROGRAM_VALUE` writes WS7 reference via
  `SetDeviationReference`. Existing HF_Locking handler likely already
  supports this — needs verification.
- **G (overlay):** New BLACS method `goto_wavelength(target_freq)`
  calling Matisse Commander VI Server `GoTo` plug-in, blocking until
  completion, then engaging the fine lock.

Code work for these is **out of scope for this doc** — it belongs in a
follow-up session with `blacs-expert` review and the GUI-local
`pid-persistence` agent at `GUIs/HF_Locking/.claude/agents/`.
