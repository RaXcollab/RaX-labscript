# Matisse C — External Locking Options

Reference for the two Sirah-supported architectures to lock a **Matisse C-S**
to an external frequency reference (in our case: a HighFinesse WS7 wavemeter
reading). Lab has a C-S model — PDH / C-X material in the manuals is **not
applicable** and is omitted here.

Sources:
- `Matisse C Manual v1.2.3` (USB stick, `Sirah USB\Matisse Commander\Manuals\`)
- `Matisse Programmer's Guide v2.4.1` (same dir)
- `Manual WS7 NeLAC` (`GUIs/HF_Locking/Manual WS7 NeLAC (1).pdf`)

## Matisse C-S piezo / scan-piezo hierarchy

| Actuator | Bandwidth | Role | Scan Piezo? |
|---|---|---|---|
| Fast Piezo (tweeter) | kHz-ish, inertia-limited | Cavity mirror; locked to ref-cell flank | No |
| Slow Piezo (tuning mirror, "woofer") | ~Hz / mechanical | Long-stroke cavity mirror; offloads Fast Piezo | **Selectable** |
| Reference cell piezo | ~Hz | Moves ref cell mode comb → shifts lock point | **Selectable (default)** |

"**Scan Piezo**" is a logical name. `Scan > Scan Device Configuration`
(Matisse Commander) picks which physical piezo it points to. Default on
C-S = reference cell piezo. Manual p.67 quote:

> "The Matisse C scans by the Scan piezo, which can be the Slow Piezo, that
> is mounted on the tuning mirror. For a stabilized Matisse C, this can also
> be the reference cell."

## Path A — External DSP Control (bypass ref cell)

```
WS7 ── DAC (P=1, I=D=0) ─────► Matisse DSP SMA (front panel, switch=Extern)
                                          │
                                          ▼
                                 Fast Piezo PID (now driven by WS7 error)
                                          │  (Slow Piezo offloads behind it)
                                          ▼
                                 Laser frequency
```

- Front-panel **Intern/Extern switch** (item 3) flipped to Extern →
  internal ref-cell error signal is electrically disconnected.
- WS7 DAC voltage = `(measured − reference) × sensitivity`. Configure WS7
  PID with **P=1, I=0, D=0** in `Settings → Laser Control Settings →
  Regulation & Sensitivity`.
- Voltage feeds the Fast Piezo PID via SMA item 4.
- **Single closed loop.** Ref cell is physically present but not in the
  error path.
- Scan = sweep WS7 reference via `SetDeviationReference()` or a time-
  function in WS7 *Reference* sheet (`triangle`, `sawtooth`, etc.).

### DSP External Input electrical spec (Manual p.145)

| Parameter | Value |
|---|---|
| Connector | SMA jack (MIL-C-39012) |
| Input voltage range | **−5.0 … +5.0 V** |
| Input impedance | **3.4 kΩ** |
| Internal normalization | input/5 V → −1.0 … +1.0 (read via `FASTPIEZO:INPUT?`) |

3.4 kΩ is low — WS7's PCI DAC drives it fine. Never insert a high-Z
attenuator or unbuffered source.

### Relevant SCPI commands (Programmer's Guide p.68–71)

Work identically whether switch is Intern or Extern; only the error source
differs:

| Command | Use |
|---|---|
| `FASTPIEZO:INPUT?` | Read DSP-input voltage normalized to −1..1 |
| `FASTPIEZO:CONTROLSETPOINT <f>` | Fast Piezo PID target |
| `FASTPIEZO:LOCKPOINT <f>` | Initial-acquisition target; smoothly slewed to CONTROLSETPOINT once locked |
| `FASTPIEZO:CONTROLSTATUS RUN\|STOP` | Engage / disengage Fast Piezo PID |
| `FASTPIEZO:LOCK?` | TRUE/FALSE — TRUE iff tweeter sits 5..95 % of its range |
| `FASTPIEZO:CONTROLPROPORTIONAL`, `:CONTROLINTEGRAL` | Fast Piezo PID gains |
| `SLOWPIEZO:LOCKPROPORTIONAL`, `:LOCKLINTEGRAL`, `:FREESPEED` | Slow Piezo follow-loop gains |

The **Intern/Extern switch has no SCPI equivalent.** Mode is a session-
level setting, not BLACS-per-shot.

## Path B — External PID plug-in (drift-correction layer)

```
WS7 measurements ─► NI-DAQ board ─► Matisse Commander External PID plug-in
                                              │  (software PID, Period ~10ms)
                                              ▼
                                   "Scan Piezo" position command
                                              │
                              ┌───────────────┴───────────────┐
                              ▼                               ▼
                   Ref Cell Piezo (default)            Slow Piezo (option)
                              │                               │
                              ▼                               ▼
                   Ref-cell flank shifts ─►          Cavity length changes ─►
                   laser tracks via internal         laser frequency moves
                   ref-cell lock                     directly

[Independently: Internal ref-cell lock active. Fast Piezo + Slow Piezo PIDs
 track the ref cell at their native bandwidth.]
```

- Internal ref-cell lock (`Main > Lock`) **stays on**. Fast Piezo runs at
  its native bandwidth against the ref cell.
- WS7 reading → NI-DAQmx Global Channel → External PID plug-in computes
  a correction → Matisse Commander moves the Scan Piezo.
- Two closed loops, but on **different actuators** (ref-cell PID acts on
  Fast/Slow Piezo; External PID acts on Scan Piezo). Formally non-
  conflicting.
- Scan = sweep External PID `Setpoint` or sweep the WS7 reference.

### External PID plug-in parameters (Manual p.137)

| Parameter | Meaning |
|---|---|
| `Process Value` | External signal (read via DAQmx Global Channel) |
| `Setpoint` | Process-value target |
| `P`, `I`, `D` | PID gains |
| `Average Width` | Number of past samples averaged before PID step |
| `Period` (ms) | Loop tick — read DAQ + compute + output new Scan Piezo voltage |
| `Activate` | Engage / disengage |
| `Protocol` | Optional file log of the run |

## Pros / cons summary

| Dimension | Path A — DSP Input | Path B — External PID |
|---|---|---|
| Closed loops | 1 | 2 (independent, different actuators) |
| Internal ref-cell lock | Disabled | Enabled |
| Fast Piezo bandwidth | Capped at WS7 update rate (~100 Hz raw) | Native (kHz-ish, locked to ref cell) |
| Drift floor | WS7 calibration (absolute) | Ref cell + WS7 (relative) |
| HF noise suppression | Worse | Better |
| HW change required | Yes (front-panel cable + switch) | No |
| PID re-tune required | Yes (Fast + Slow Piezo from scratch) | No (factory ref-cell gains apply) |
| Per-shot remotable mode-switch | No (HW switch) | Yes (software) |
| NI-DAQ in lock-critical path | No | Yes |
| Reversibility | Walk to laser, flip switch | Toggle software off |
| Sirah-supported workflow | Custom / advanced | Documented plug-in |
| Approx. == current (failing) setup | No | **Yes** |

## When to pick which

**Pick Path A (DSP Input) iff:**
- Ref-cell drift is the dominant noise source (verified empirically — see
  diagnosis below) **and**
- The lab can tolerate losing the high-bandwidth ref-cell-to-Fast-Piezo lock.

**Pick Path B (External PID plug-in) iff:**
- Diagnosis shows ref-cell drift is small and the current instability is
  caused by mis-tuned external servo parameters (loop period, gains,
  averaging window). Fix the tuning.

**Diagnosis before committing:**
1. With internal ref-cell lock ON and any external software servo
   DISABLED, monitor `FASTPIEZO:LOCK?` and the WS7 reading for ≥10 min.
2. If WS7 drift is small relative to the lab's frequency budget → Path B
   is viable; fix tuning.
3. If WS7 drift is large → ref cell itself is the problem; Path A is
   justified.

## WS7 as error-signal source (Path A) or process value (Path B)

| Parameter | Built-in WS7 DAC | External PCI DAC |
|---|---|---|
| Output range | ±4.096 V | ±10.0 V |
| Resolution | 0.125 mV (16-bit) | 16-bit |
| Step time (`drive immediately`) | ~200 µs/step | same |
| Connector | LEMO at rear | D-Sub on PCI card |

External PCI DAC ±10 V exceeds Matisse ±5 V. Set WS7 *Bounds > Signal
Bounds* (Manual §3.5.3) to ±4 V to clip.

### Deviation-mode configuration (Path A)

In `Settings → Laser Control Settings`:

- **Reference** (§3.5.1): set the lock-target wavelength. For scans, enter
  a time function (`triangle(t/period)*scan_width + center`) — or hold
  constant and sweep `SetDeviationReference()` from the API.
- **Regulation & Sensitivity** (§3.5.2): **P = 1, I = 0, D = 0**.
  Sensitivity sized so ±50–100 MHz of detuning ≈ ±1 V at the DAC
  (≈ ±0.2 normalized at the Matisse, similar to the recommended PDH
  error-signal operating range).
- **Bounds** (§3.5.3): clip at ±4 V. Enable `drive immediately`.
  Set `Maximum shot-per-shot change` to ~50 mV as a runaway safety net
  during initial commissioning.
- **Polarity**: pick one, ready to flip after the first lock attempt — sign
  of `(measured − reference)` × Fast-Piezo gain must give negative feedback.
- **Activate** the regulation signal.

### Process-value configuration (Path B)

WS7 just outputs its standard measurement to the NI-DAQ card (or directly
via DLL `GetFrequency`). The Matisse External PID plug-in does the PID.
WS7's own PID is **off** in this mode.

### Relevant WS7 DLL functions

Same set whether Path A or Path B:

- `SetDeviationMode`, `SetDeviationReference`, `SetDeviationSensitivity`
- `GetDeviationSignal[Num]` — current DAC voltage (diagnostic)
- `GetFrequency[Num]` — raw measurement (Path B)

WS7 data cadence: ~5 Hz per channel, ~40 Hz aggregate over 8 channels with
fiber switcher — see [hf-locking-rates.md](hf-locking-rates.md).

## Operational caveats (both paths)

- **C-S lab, no PDH board** — `POUNDDREVERHALL:*` commands and the
  `PDH:CONTROL` bit-4 intern/extern selector do **not** apply. Do not
  confuse `PDH:CONTROL` bit 4 (PDH board internal switch, C-X only) with
  the front-panel DSP Intern/Extern switch.
- **Confirm Matisse firmware ≥ 1.4** via `*IDN?` — older firmware lacks
  the `LOCKPOINT` / `CONTROLSETPOINT` split.
- **WS7 measurement gaps** (exposure auto-adjust, channel-switching
  pauses, insufficient-light errors) cause the DAC / measurement stream
  to hold last value. In Path A this means the Fast Piezo sees a flat
  zero-error signal and drifts during the gap. Mitigate with WS7 *Bounds*
  + small shot-per-shot change.
- **Path A only — no interlock** between the Intern/Extern switch and
  software state. Extern with no signal cable connected = Fast Piezo
  locks to 0 V error. Physical label on the front panel + a startup
  `FASTPIEZO:INPUT?` sanity check is recommended.
- **Don't run both paths simultaneously.** Pick one. Path A's "ref cell
  disconnected" state and Path B's "ref cell driven by software PID" are
  not compatible.

## BLACS integration touchpoints

Per-shot mode switching is **not** possible for Path A (HW switch). For
either path, BLACS sees:

- `LaserLockDevice` ([userlib/user_devices/LaserLockDevice/](../userlib/user_devices/LaserLockDevice/))
  already speaks to the WS7 via the HF_Locking GUI's ZMQ. Add a "deviation
  reference" command if scanning needs to be per-shot.
- New ZMQ commands needed: `set_deviation_reference(wavelength)`,
  `get_deviation_signal()`, `read_fastpiezo_lock()`, `read_fastpiezo_input()`.
- Matisse SCPI access (USB/RS232) is **separate** from the WS7 path. The
  Matisse SCPI commands listed above need their own driver if BLACS-side
  Fast Piezo lock readback is required. Currently the lab does not have a
  BLACS device for direct Matisse SCPI control — adding one is out of
  scope for this doc.

## Out of scope for this document

- Specific PID gain values for either path (depend on hardware
  measurements not yet made).
- The diagnosis sequence in §"When to pick which" — that is a lab task,
  not a software task.
- Any new BLACS device class for direct Matisse SCPI control.
