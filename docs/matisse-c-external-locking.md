# Matisse C-S External Locking — Candidate Architectures

Reference for the laser-lock architectures available on a **Matisse C-S** +
HighFinesse **WS7 NeLAC** with an 8-channel fiber switcher.

**Rewritten 2026-05-23 after deep-diving the Matisse Programmer's Guide
Chapters 4 + 5, the Plug-ins help PDF in full, the Matisse Commander
`Addons\LabVIEW - Matisse Commander.zip` (including Sirah's official
`DLLcall_Network.py` example), and the LocalGoTo plug-in source
(`Addons\LabVIEW - MCP LocalGoTo.zip`).** Earlier versions of this doc
inferred APIs that don't exist (Counterdrift remote setpoint) and missed
the LocalGoTo plug-in entirely. Mechanisms below are reported strictly
from official Sirah sources + the installed plug-in code, not from
guesses.

Sources:
- `Matisse C Manual v1.2.3` (`Sirah USB\Matisse Commander\Manuals\`)
- `Matisse Programmer's Guide v2.4.1` (same dir, Chapters 4 + 5)
- `Manual WS7 NeLAC` (`GUIs/HF_Locking/Manual WS7 NeLAC (1).pdf`)
- Matisse Commander Plug-ins help PDF (29 pages, operator-supplied)
- Local install: `C:\Program Files (x86)\Sirah-1\Matisse Commander\`
  (and Sirah-2)
- Addon zips containing official Sirah Python + LabVIEW examples

## 2026-07-15 — UI automation ruled out; SCPI/Network-Server path VERIFIED

Empirical results from live read-only probing (TiSa-2 / Sirah-2, C-S now at
736 nm for BaF X(1)-B(0)). Supersedes the "three theoretical paths" pessimism
in §1 for the *no-LabVIEW* case, and corrects the earlier assumption that
Counterdrift shares Candidate W's fragility — the operator bench-tested
Counterdrift holding through setpoint steps where the WS7-direct PID breaks.

### Dead ends (verified this session)
- **Counterdrift GUI is NOT automatable.** Matisse Commander is a LabVIEW app;
  its front panel — including the live Counter Drift dialog — is a single drawn
  canvas exposing **0** controls to both Windows UI Automation *and* Win32
  child-window enumeration (verified on both instances + the actual dialog).
  pywinauto/UIA is a dead end; do not attempt it.
- **No `COUNTERDRIFT:*` command** exists in the full 306-command device set
  (Programmer's Guide Ch. 6). Counterdrift's setpoint is reachable ONLY via a
  custom LabVIEW plug-in. LabVIEW 2020 32-bit is NOT installed here (only
  2023-2026 folders, none with LabVIEW.exe) — the plug-in path is blocked until it is.
- **No VI-Server / ActiveX / OLE channel** — the app configs carry no
  `server.tcp.*` / `server.ole.*` keys and expose no such listening port.

### The working no-LabVIEW channel: Matisse Network Server (SCPI)
- Per Matisse Commander instance; **default OFF**. Enable via
  `Matisse > Communication Options`: Network Client = **Use VISA**, Network
  Server = **Enable Server** (default port 30000). Both installs default to
  30000 → on one PC they collide; give each a distinct port.
- **Wire framing = LabVIEW length-prefixed, NOT newline SCPI:**
  send `struct.pack('>L', len(payload)) + payload` (ASCII, no newline); recv a
  4-byte big-endian length then that many bytes; close gracefully with
  `Close_Network_Connection` + 300 ms. Raw newline SCPI → server **Error 56**
  ("TCP Read exceeded time limit") + aborted connection. Reference client:
  `nelsond/sirah-matisse-commander` (endorsed by Programmer's Guide Ch. 3).
- Read-only probe: `GUIs/HF_Locking/tools/matisse_scpi_probe.py` (queries only;
  safe on a live, locked laser).

### Verified reads (TiSa-2)
- `SCAN:DEVICE = 2` → scan master is the **reference-cell piezo** (the actuator
  Counterdrift drives). Scan limits 0.1-0.9; `SCAN:RISINGSPEED = 1e-3`.
- `SCAN:NOW` and `REFERENCECELL:NOW` **read identical at one instant** (0.261683);
  likely the same underlying value, but that is a single sample, not proof.
- So the ref-cell position *appears* remotely settable via `SCAN:NOW` /
  `REFERENCECELL:NOW` — no LabVIEW, no GUI.
- `IDN?` is **unreliable on TiSa-2** (reports "Matisse TR / S/N 99-99-99"; it is
  a real **C-S**, real S/N 24/38/18 — firmware serial bug; TiSa-1 reports fine).
  Never gate logic on IDN for this unit.

### Candidate path (untested — needs pump ON + laser locked)
Drive `SCAN:NOW` for the coarse, gentle frequency hop (the Matisse's native
tuning path, which the internal lock is designed to follow) + keep the existing
WS7/HF_Locking wavemeter servo for drift/hold. Integrate as a per-channel
backend in HF_Locking (`workers.py`) for ports 4 (TiSa_1) / 6 (TiSa-2).
**Open questions:** does an arbitrary-order `SCAN:NOW` step hold the internal
lock (vs WS7 steps that break it)? position→THz calibration
(`SCAN:REFERENCECALIBRATION?` returned a syntax error; use Control Scan
Measurement instead).  If it holds, no LabVIEW is needed.

### Verified 2026-07-15 (code-read)
- ZMQ is **v1**; command surface is exactly `HELLO` / `CHECK_VALUE` /
  `PROGRAM_VALUE` — **no lock enable/disable command** (arming is GUI-manual-only).
  `workers.py:_handle_msg` (L565-602).
- **Wait-gate** `if wait and lock_enabled and dev_mode:` — for a Counterdrift/SCPI
  port the WS7 `deviation_mode` is OFF → gate False → `PROGRAM_VALUE` returns
  SUCCESS *without waiting for convergence* (the silent lock-bypass to fix).
- Port map: **connection 4 = TiSa_1, connection 6 = TiSa_2** (`connection_table.py`
  L56-95; GUI `CHANNEL_NAMES` labels port 6 "Ch_6" but BLACS names it TiSa_2);
  `LaserLockDevice(..., wait_for_lock=True)`.

### Still unverified — confirm before building
- `SCAN:NOW == REFERENCECELL:NOW` being the *same* actuator — one coincident read;
  confirm by moving one and reading the other (part of the gated write test).
- LaserLockDevice `transition_to_manual` no-op / `post_experiment` teardown —
  recon claim; verify in `LaserLockDevice/blacs_workers.py` before relying.

## Lab-confirmed operating context

| | |
|---|---|
| Laser | Matisse C-S (side-of-fringe ref cell, no PDH / no EOM) |
| Primary use | Scanning high-power tunable Ti:Sa — spectroscopy + cooling + imaging + repump |
| Stability budget | ~1 MHz, seconds-to-minutes (current achievable WS7-limited floor) |
| Per-shot scan | Sub-MHz step resolution, 5–10 MHz steps within ~500 MHz envelope, **arbitrary frequency order** |
| Wavemeter | HighFinesse WS7 NeLAC, 8-channel fiber switcher, ~5 Hz/channel, ~40 Hz aggregate |
| Current lock | WS7 built-in 8-channel PID DAC card, configured via HF_Locking GUI (`GUIs/HF_Locking/`) over `wlmData.dll` |
| Matisse Commander install | `C:\Program Files (x86)\Sirah-1\Matisse Commander\` (and Sirah-2). Version 1.27.0.0 per Changelog |

## Matisse C-S piezo / scan-piezo hierarchy

| Actuator | Bandwidth | Role | Scan Piezo? |
|---|---|---|---|
| Fast Piezo (tweeter) | kHz-ish | Cavity mirror; chases ref-cell flank in internal lock | No |
| Slow Piezo (tuning mirror, "woofer") | ~Hz | Long-stroke cavity mirror; offloads Fast Piezo | Selectable |
| Reference cell piezo | ~Hz | Moves ref-cell mode comb → shifts lock point | **Selectable (default on C-S)** |

`Scan > Scan Device Configuration` (Matisse Commander) picks which
physical piezo the logical "Scan Piezo" points to.

## What's officially documented for external use (Programmer's Guide Ch. 4–5)

Chapter 4 documents the **general MCP_\* plug-in interface** (custom
plug-in with Main VI that receives command strings: `AppInit`, `AppClose`,
`Version`, plus menu-item tags).

Chapter 5 documents the **Wavemeter Plug-in interface** and explicitly
lists **two** sub-VIs callable from your own plug-in or external LabVIEW
project:

| Public callable VI | Source LLB | Inputs |
|---|---|---|
| `MCP WM Goto Wavemeter Position Wait or Stop.vi` | `MCP Wavemeter.llb` | Communication resource, config-file refnum, destination freq (GHz), Positions Mode (opt), Create Report (opt) |
| `MCP Extended Scan Wait or Stop.vi` | `MCP Wavemeter.llb` | Communication resource, config-file refnum, Scan From (GHz), Scan To (GHz), Scan velocity, Create Report (opt) |

Plus the supporting plumbing (`Get Read Wavelength extern Settings.vi`,
`MCP WM Find ini file.vi`, `MCP HighFinesse Initialize Wavemeter.vi`,
etc.) for use outside Matisse Commander.

**Counterdrift is deliberately omitted.** Chapter 5 names the
publicly-callable VIs and Counterdrift isn't one. The Plug-ins help PDF
describes Counterdrift only as a GUI dialog. The Changelog mentions
Counterdrift only for GUI-side fixes (parameter bounds, save persistence,
Max-Diff/s setting). There is no public Sirah API to drive Counterdrift's
Setpoint from outside the Matisse Commander process.

**LocalGoTo (separate plug-in, `MCP LocalGoTo Plug-In.llb`)** is also not
in Chapter 5's public-callable list — only the full GoTo is documented.
But the LocalGoTo source ships in `Addons\LabVIEW - MCP LocalGoTo.zip`
and its `MCP LocalGoTo Plug-In.lvproj` imports the documented
`MCP WM Goto Wavemeter Position Wait or Stop.vi` as a dependency, so the
two are designed to interoperate.

## The Matisse Commander Network Server (Programmer's Guide Ch. 3)

TCP server inside the running Matisse Commander process. Configurable.
**Default port 30000** (per Sirah's `DLLcall_Network.py`). Acts as a
**VISA pass-through** — accepts SCPI commands over TCP, relays them to
the Matisse hardware via Matisse Commander's existing USB-VISA
connection, returns SCPI responses.

Operational characteristics (from `Changelog.md` v1.26.3 + v1.26.8.5):
- TCP text protocol
- 1024-byte receive buffer
- 5 ms send timeout, 50 ms receive timeout
- Nagle algorithm disabled (low latency)
- Reconnect supported

**The Network Server does NOT expose plug-in commands.** It is VISA
passthrough only. `GoToPosition_Network.vi` works by implementing the
GoTo algorithm in the **calling-side DLL** and sending SCPI motor/piezo
commands through the Network Server transport.

The Sirah-supplied Python example (`DLLcall_Network.py`, verbatim):

```python
import ctypes
dll = ctypes.CDLL(r".\build\MatisseDLLExample.dll")
dll.GoToPosition_Network.argtypes = [ctypes.c_double, ctypes.c_char_p, ctypes.c_long]
ip_address = ctypes.create_string_buffer(bytes('192.168.115.72','utf-8'))
port = 30000
exit_code = dll.GoToPosition_Network(360000.0, ip_address, port)   # GHz, ip, port
# exit_code 0 = OK
```

Caveats from the official example:
- **Python 3.6+ 32-bit required** (LabVIEW DLL is 32-bit)
- *"Make sure no other connections to the laser are currently open."*
- All DLL dependencies (`Wavemeter` directory, packed libraries) must be
  co-located with the DLL.
- Settings loaded from `%USERPROFILE%\AppData\Local\Sirah\Matisse Commander`

**⚠ The pre-built `MatisseDLLExample.dll` is NOT shipped.** The Addon
zip contains only `ExampleProject.lvproj` + `.vi` source. To use this
path you must either:
- **Build the DLL** from source in LabVIEW 2020 32-bit (requires LV
  license), or
- **Re-implement the GoTo algorithm in pure Python** talking directly to
  the Network Server's text protocol (see `nelsond/sirah-matisse-commander`
  GitHub repo as a reference — Programmer's Guide Ch. 3 explicitly points
  at it as "A Python module implementing such a connection").

## 0 — Baseline architecture (Candidate W): current WS7-direct PID

What's running today.

```
WS7 (8-ch fiber switch, ~5 Hz/ch) ── wlmData.dll
       │ in HF_Locking WavemeterWorker thread
       ▼
WS7 built-in 8-channel PID DAC card (Sirah-supplied wavemeter PID)
   ch4 (TiSa_1) config: P=0.16, I=0.84, D=0.034, T=0.02, dt=0.01, UseTa=1,
                        Polarity=-1, SensitivityDim=-2, Bounds 0..9000 mV
       │
       ▼ DAC voltage on ch4 (~0..5 V in practice)
       │ rear-panel SMA cable
       ▼ Matisse C Reference Cell external input (item 13)
       │
       ▼ ref-cell piezo moves → ref-cell mode comb shifts → flank position moves
       │
       ▼ Internal Matisse ref-cell lock (chases moving flank):
            Fast Piezo PID (kHz) + Slow Piezo offload (Hz)
       │
       ▼ Laser frequency ── back into WS7 → loop closes
```

HF_Locking GUI is the monitor + ZMQ comms layer (configures WS7 PID via
DLL, broadcasts WS7 readings to BLACS, exposes setpoints + lock indicators
via `LaserLockDevice`). Does NOT run its own PID loop.

Structurally equivalent to the Matisse Commander Counterdrift plug-in,
just implemented via the WS7's own PID instead of Sirah's plug-in.

### Why it's painful

See §6 for the operator-confirmed failure mechanism: arbitrary-order
setpoint hops break the internal ref-cell lock → Slow Piezo enters
`FREESPEED` search mode → laser walks off-mode → mode-hop or operator
recovery.

## 1 — Candidate C: Counterdrift plug-in — set-and-hold only

`Plug-ins > Wavemeter > Counterdrift` is fully usable as a **static
drift compensator** with no engineering work. Operator sets the Setpoint
manually via the dialog, hits Activate, leaves it running. The PID holds
the laser at that wavelength, compensating slow drift via ref-cell piezo
adjustments.

**For per-shot BLACS scanning at sub-MHz precision: NO Sirah-documented
API exists for setting Counterdrift's Setpoint remotely.** Confirmed by
reading the entire Plug-ins help PDF + Chapter 4 + Chapter 5 of the
Programmer's Guide + Changelog.md. Counterdrift appears in the Changelog
only for GUI-side fixes (parameter bounds, persistence).

### Configuration (set-and-hold mode)

- Front-panel cable: unchanged (WS7 ch4 still to rear-panel item 13) —
  cable serves no purpose now but doesn't interfere
- Disable WS7 PID for ch4 (`SetDeviationMode(0)` via HF_Locking, or in
  the WS7 native app)
- Enable WM Selector (or HighFinesse) plug-in for the data layer, plus
  the Wavemeter plug-in for the umbrella
- `Settings → WM Selector → Show Settings`: `Switch = TRUE`, `Channel = 4`,
  `Synchronous Wavemeter Readout? = ON` (required for 8-channel switched WS7)
- Open `Plug-ins > Wavemeter > Counterdrift` dialog
- Sirah-suggested start: **P=0, I=−0.5, D=0, Average=10, Update=300 ms**
- `Synchronous Wavemeter Readout?` = ON
- `AutoReset` = **OFF** initially (its docs warn AutoReset can cause
  100s-of-MHz-to-GHz frequency jumps on C-S; not what we want during
  shots)
- `Set to current position` → `Activate`
- Internal Matisse `Main > Lock`: stays ON (Counterdrift's
  Laser-Locked? interlock requires it)

### For per-shot remote setpoint (NOT recommended without significant work)

Three theoretical paths, none Sirah-documented:

| Path | Effort | Risk |
|---|---|---|
| Custom MCP_\* plug-in using in-process VI Server to write to the Counterdrift dialog's Setpoint control | LabVIEW 2020 32-bit license + ~1 week LV work + reverse-engineering the VI hierarchy in `MCP Wavemeter.llb` | High — Matisse Commander upgrades can rename VIs silently |
| External LabVIEW VI Server access from Python | A few days of LV protocol work | Same as above + bitness mismatch (LV 32-bit, Python 64-bit) requires bridge process |
| OS-level UI automation (mouse/keyboard) | Trivial | Catastrophic — unreliable, slow, breaks on layout change |

## 2 — Candidate A: DSP External Input bypass

**Removes the internal ref-cell lock entirely.** WS7 deviation voltage
feeds the Matisse Fast Piezo PID directly via the front-panel DSP
External Input SMA (item 4).

### Differences from W

| | W | A |
|---|---|---|
| Cable termination | Rear item 13 (Reference Cell external) | Front item 4 (DSP External Input) |
| Front-panel switch (item 3) | Intern | **Extern** |
| Internal ref-cell lock | ON | **OFF** (`Main > Lock` disabled) |
| WS7 PID mode | Full PID (P=0.16, I=0.84) | **Deviation-only** (P=1, I=0, D=0) |
| Actuator driven | Ref cell piezo | Fast Piezo (via Matisse FAST PIEZO PID) |
| Closed loops | 2 (WS7 PID + internal ref-cell lock) | **1** (WS7 deviation → Matisse Fast Piezo PID) |
| Matisse Fast Piezo PID gains | Factory ref-cell values | **Must be re-tuned from scratch** — factory gains assume ref-cell photodiode signal |

### Configuration

**Hardware:**
- Move SMA cable: rear item 13 → front item 4
- Flip front-panel switch (item 3) to **Extern**
- Physical label near switch: "Extern = WS7 deviation. Verify signal before engaging."

**WS7 (deviation mode):**
- Set P=1, I=0, D=0 explicitly via DLL (HF_Locking `config.py` registries
  already cover the relevant constants)
- Sensitivity: scale so ±500 MHz fits inside ±4 V
- Bounds: clip at ±4 V (`BoundsMin=-4000`, `BoundsMax=4000`)
- Polarity: determined empirically on first lock (flip if diverges)

**Matisse C:**
- `Main > Lock` OFF
- `FASTPIEZO:CONTROLPROPORTIONAL`, `:CONTROLINTEGRAL`: start at ~10× below
  factory values; ramp up while watching `FASTPIEZO:NOW?` for ringing
- `SLOWPIEZO:LOCKPROPORTIONAL`, `:LOCKLINTEGRAL`: same approach
- `FASTPIEZO:CONTROLSETPOINT 0.0` (DSP input = 0 V = WS7 at setpoint)

### Per-shot scan path

BLACS sets the WS7 **reference** (not the setpoint) via
`SetDeviationReference`. The Fast Piezo PID chases the new error-signal
zero automatically. **No setpoint-step transient on the Matisse side.**

### Hypothesis (untested)

Eliminates the failure-mode chain in §6: no internal ref-cell lock to
drop, no Slow Piezo search to trigger. Setpoint changes propagate via
Fast Piezo motion (smoothest actuator on a C-S) rather than via ref-cell
mode shift.

### What's lost

Nothing the lab needs: the lab is already WS7-noise-limited at ~1 MHz,
so the internal ref-cell-to-Fast-Piezo lock was contributing fragility
without contributing stability.

## 3 — Candidate G: GoTo via Network Server (the supported remote path)

`Plug-ins > Wavemeter > GoTo` is a coordinated re-tune procedure
(BiFi + Thin Etalon + Piezo Etalon + Slow Piezo + Ref Cell Piezo all
moved together to reach a target wavelength). Survives mode hops.
Documented for external invocation via Sirah's compiled DLL example.

### Per-call latency (estimated)

| Hop type | Steps run | Approx duration |
|---|---|---|
| **In-mode** (within one Piezo Etalon FSR ≈ 18 GHz) | Skip BiFi/TE full scans, mini-tune PE + Slow Piezo + Ref Cell + lock + final fine slew | ~1–3 sec |
| **Cross-TE-mode** (>~5 GHz with mode change) | Full TE scan + downstream | ~10 sec |
| **Cross-BiFi-mode** (>~50 GHz with mode change) | Full BiFi + TE + downstream | ~20–40 sec |

Our 500 MHz envelope is all in-mode → expect ~1–3 sec/shot. Sets max
shot rate at roughly **0.3–1 Hz** with full-GoTo per shot.

### Implementation paths

**Path G.1 — Sirah's Network DLL (documented, easiest if you have LV)**

Use `GoToPosition_Network(double GotoPositionGHz, char NetworkAddress[],
int32_t Port)` from Sirah's `MatisseDLLExample.dll`. Verbatim Python
template in `DLLcall_Network.py`. Requires:
- **Build the DLL from source in LabVIEW 2020 32-bit** (it's not
  pre-built in the shipped Addon zip)
- Python 3.6+ 32-bit
- Matisse Commander running, Network Server enabled on a known port
- All DLL dependencies (`Wavemeter`, `MCP Wavemeter.llb`, etc.) in the
  build folder

**Path G.2 — Custom MCP_\* plug-in calling `MCP WM Goto Wavemeter
Position Wait or Stop.vi` directly (documented, no Network Server)**

Build a custom plug-in (Chapter 4 framework) that opens a TCP listener
and internally calls the public GoTo VI. Inputs: communication resource +
config-file refnum (provided by Matisse Commander), destination
frequency in GHz. Advantages over G.1:
- No need to coordinate the calling-side DLL with the Matisse-side
  Network Server
- Same in-process VI call as Matisse Commander's own menu item
- Still requires LabVIEW 2020 32-bit license + ~3 days LV work

**Path G.3 — Pure-Python Network Server client**

Implement GoTo's algorithm in Python: open TCP to Matisse Commander's
Network Server (port 30000 default), send SCPI motor/piezo commands
directly. Doesn't need LabVIEW license. But reproduces ~1000 lines of
LabVIEW GoTo logic in Python — significant work. Programmer's Guide
points at `nelsond/sirah-matisse-commander` GitHub repo as a starting
reference.

### Tuneable knobs (set once via `Plug-ins > Wavemeter > GoTo Position &
Extended Scan Options`)

| Knob | Default | What to tune for us |
|---|---|---|
| `Precision [GHz]` | 0.01 (10 MHz) | Drop to **0.001 (1 MHz)** for sub-MHz scans |
| `Scan velocity for reset [1/s]` | 0.01 | Faster = less per-shot latency, but risk of overshoot |
| `Max retries after error` | 2 | Reasonable default |
| `Delay after locking [ms]` | 2000 (X-class) | Reduce for C-S; ref-cell PID re-engages quickly |
| `Abort scan on jump detection` | ON | Leave on — catches mid-procedure mode hops |
| `Enable Control Scan` | ON | Auto-tunes scan-PID parameters during operation |

### Prerequisites

- **Birefringent Filter Calibration** (`Plug-ins > Wavemeter > Birefringent
  Filter Calibration`) — auto-scans BiFi, maps motor position → wavelength.
  Done once per laser config (mirror swap, MOS change). Saved in
  Matisse Commander config.
- **Control Scan Measurement** (`Scan > Control Scan Measurement`) —
  measures MHz / scan-device-unit conversion factor. Done once per
  scan-device choice (Ref Cell vs Slow Piezo). Saved in config.

Both prerequisites established once by the operator per session/laser
configuration. Persist across Matisse Commander restarts.

## 4 — Candidate L: LocalGoTo plug-in (NEW — not in earlier doc revisions)

`Plug-ins > Wavemeter > LocalGoTo` is a **separate Sirah plug-in**
(`MCP LocalGoTo Plug-In.llb`) optimized for **in-mode hops**. Its
algorithm (from inspecting `Addons\LabVIEW - MCP LocalGoTo.zip` source):

1. **Calc RefCell Position** — uses LocalGoTo's own calibration table to
   directly compute the ref-cell piezo voltage corresponding to target
   frequency (no BiFi/TE scan)
2. **Calc piezo jump** — computes the piezo motion required
3. **Set RefCell + Slow Piezo + PZETL** — applies the jump
4. **Wait For Fast Piezo Lock** — confirms lock re-acquires
5. **Scan To Goal** — final fine slew if needed
6. If any of the above fails (target outside current mode etc.), **falls
   back to the documented full GoTo VI** (`MCP WM Goto Wavemeter Position
   Wait or Stop.vi` — imported as a dependency in the LocalGoTo
   `.lvproj`)

### Per-call latency (estimated)

| Hop type | Path taken | Approx duration |
|---|---|---|
| **In-mode, in calibration window** | Direct piezo jump + Fast Piezo Lock wait + fine slew | **~100–500 ms** |
| **Outside calibration window or mode-change required** | Fall back to full GoTo | ~1–3 sec |

For our 500 MHz envelope, all hops should land in the fast path → max
shot rate **~2–10 Hz**. Significantly better than full GoTo.

### Caveats

- **NOT documented for external invocation.** Chapter 5 lists only the
  full GoTo and Extended Scan as public-callable. LocalGoTo's VIs
  (`MCP LocalGoTo Set Laser To.vi`, etc.) are not in the public list.
- Architecturally feasible to call from a custom MCP_\* plug-in (same
  pattern as the documented GoTo) — but Sirah doesn't promise the API
  stability of LocalGoTo VIs.
- Has its own calibration step (`MCP LocalGoTo Calibrate.vi`) that's
  distinct from BiFi Calibration + Control Scan Measurement. Operator
  would need to characterize this and ensure it's saved.

### Implementation path

Same as Candidate C's per-shot remote scenario: **custom MCP_\* plug-in**
that exposes a TCP listener and internally calls `MCP LocalGoTo Set
Laser To.vi`. ~1 week LabVIEW work + LV 2020 license. Higher payoff
than the same effort for Counterdrift because:
- LocalGoTo is purpose-built for in-mode hops (our use case exactly)
- It actively re-tunes per call → no "ref-cell lock breaks" failure mode
- It already has the Fast-Piezo-Lock wait built in
- Falls back to documented GoTo for out-of-mode → safety net

## 5 — Paths NOT being tested (with reasons)

| Path | Why ruled out |
|---|---|
| **External PID plug-in** | Same architecture as Counterdrift (ref-cell-piezo-driven PID on top of internal lock) but requires NI-DAQmx Global Channel + analog process value we don't have. Strictly dominated by Counterdrift. |
| **Strain Gauge plug-in** | Requires strain gauge physically glued to the piezo. Not installed. |
| **HighFinesse / WM Selector standalone** | Data layer only, not lock loops. We already have equivalent functionality via `wlmData.dll` direct from HF_Locking GUI. |
| **PZA plug-in** | Sirah piezo-amplifier card option. Different scan-range hardware. Not a lock architecture. |
| **Picoscrew plug-in** | Beam alignment + wavelength-range switching. Not lock-related. |
| **MCP MenloComb / Gentec Maestro / Keysight / TDS** | Other instruments. Not lock-related. |

## 6 — Comparison matrix

Acceptance test (same for W, C set-and-hold, A, G, L): 100-shot BLACS
sequence, sub-MHz step resolution, 5–10 MHz hops in arbitrary order
within ~500 MHz envelope. Metrics: lock-loss count, σ at fixed setpoint,
settling time, mode-hop count, Slow Piezo search invocations.

| Candidate | Engineering cost | Per-shot latency | Max shot rate | Documented? |
|---|---|---|---|---|
| **W** (current) | 0 — already running | ms (when working) | 10+ Hz | Internal — we own it |
| **C — set-and-hold** | 0 — GUI config only | N/A (no per-shot control) | N/A | Documented |
| **C — per-shot** | LV 2020 license + 1+ week LV work | ms | 10+ Hz | **NOT documented** |
| **A** | HW cable move + Matisse PID re-tune | ms | 10+ Hz | Documented |
| **G via Path G.1 (Network DLL)** | LV 2020 license + DLL build + Python wrapper | ~1–3 sec in-mode | ~0.3–1 Hz | Fully documented |
| **G via Path G.2 (custom plug-in)** | LV 2020 license + ~3 days LV work | ~1–3 sec in-mode | ~0.3–1 Hz | Documented public VI |
| **G via Path G.3 (Python Network client)** | ~1+ week Python work, no LV needed | ~1–3 sec in-mode | ~0.3–1 Hz | Transport doc'd, client custom |
| **L (LocalGoTo)** | LV 2020 license + ~1 week LV work | ~100–500 ms | ~2–10 Hz | **NOT documented** for external |

Picking the winner is a Pareto-front question across these costs +
behavior, not a single-axis maximum.

## 7 — Failure mechanism of Candidate W (operator-confirmed, 2026-05-22)

**What happens when BLACS step-changes a setpoint:**

1. BLACS writes new setpoint to WS7 ch4 via `SetPIDCourseNum`.
2. WS7 PID sees ~5–10 MHz step error.
3. WS7 PID drives ref-cell DAC voltage toward new equilibrium —
   aggressive because integral wind-up tuned for continuous tracking.
4. Ref-cell piezo moves → ref-cell mode comb shifts → flank position
   moves.
5. **Internal Matisse ref-cell lock breaks** — Fast Piezo can't track
   moving flank, swings past 5%/95% threshold → `FASTPIEZO:LOCK?` = FALSE
   (per Programmer's Guide p.68).
6. Slow Piezo enters `SLOWPIEZO:FREESPEED` search mode (per Matisse
   Manual: "in the not-locked case, [Slow Piezo] will scan the laser to
   a resonance of the reference resonator").
7. Slow Piezo sweeps cavity length in one direction looking for a
   ref-cell flank to re-lock to.
8. Cavity length changes → Piezo Etalon waveform shakes (downstream
   effect, NOT cause).
9. Re-locks possibly on wrong mode → wrong frequency, OR operator gives
   up.

**Why operator's previously-tried fixes don't work:**

| Tried | Why it didn't help |
|---|---|
| Reduced WS7 PID I gain | Scans become too slow to be useful |
| Capped `cmiDeviationMaxChangePerShot` | Per-measurement cap, but multi-cycle integration still moves ref cell enough to break lock |
| Tuned close in frequency | Doesn't help — any useful step still breaks |
| Continuous ramps via `Scan > Scan Setup` | Works, but experiment needs arbitrary order |

**The architecture itself — internal ref-cell lock as inner loop, driven
by an outer servo on the ref-cell piezo — is the source of fragility**
regardless of who drives the ref cell (WS7 PID in W, Counterdrift in C,
External PID plug-in).

## SCPI command reference (works in all candidates)

| Command | Use |
|---|---|
| `FASTPIEZO:INPUT?` | Read DSP-input voltage normalized to −1..1 (Intern or Extern) |
| `FASTPIEZO:CONTROLSETPOINT <f>` | Fast Piezo PID target |
| `FASTPIEZO:LOCKPOINT <f>` | Initial-acquisition target; slewed to CONTROLSETPOINT |
| `FASTPIEZO:CONTROLSTATUS RUN\|STOP` | Engage / disengage Fast Piezo PID |
| `FASTPIEZO:LOCK?` | TRUE iff tweeter sits 5–95 % of range |
| `FASTPIEZO:CONTROLPROPORTIONAL`, `:CONTROLINTEGRAL` | Fast Piezo gains |
| `SLOWPIEZO:LOCKPROPORTIONAL`, `:LOCKLINTEGRAL`, `:FREESPEED` | Slow Piezo gains + search-mode speed |

**Intern/Extern switch (item 3) is hardware-only.** No SCPI equivalent.
Mode is a session-level commitment for Candidate A.

## DSP External Input electrical spec (Candidate A)

Matisse C Manual p.145:

| Parameter | Value |
|---|---|
| Connector | SMA jack (MIL-C-39012) |
| Input voltage range | **−5.0 … +5.0 V** |
| Input impedance | **3.4 kΩ** |
| Internal normalization | input/5 V → −1.0 … +1.0 (via `FASTPIEZO:INPUT?`) |

3.4 kΩ is low — WS7's PCI DAC drives it fine. Never insert a high-Z
attenuator.

## WS7 deviation-mode configuration (Candidate A)

| Parameter | Built-in WS7 DAC | External PCI DAC |
|---|---|---|
| Output range | ±4.096 V | ±10.0 V |
| Resolution | 0.125 mV (16-bit) | 16-bit |
| Step time (`drive immediately`) | ~200 µs/step | same |
| Connector | LEMO at rear | D-Sub on PCI card |

For Candidate A: WS7 in deviation mode (P=1, I=0, D=0), sensitivity sized
so ±500 MHz fits inside ±4 V. Bounds at ±4 V. Polarity empirical.

WS7 DLL functions (already wrapped in HF_Locking `wlm_utils.py`):
`SetDeviationMode`, `SetDeviationReference`, `SetDeviationSensitivity`,
`GetDeviationSignal[Num]`, `GetAnalogIn`.

## BLACS integration touchpoints

For all candidates, WS7 communication exists in
`userlib/user_devices/LaserLockDevice/` over ZMQ (REQ-REP port 3796 +
PUB-SUB port 3797). Candidate-specific additions:

| Candidate | BLACS-side change |
|---|---|
| **W** (today) | `PROGRAM_VALUE` → `SetPIDCourseNum`. No code change. |
| **C — set-and-hold** | No BLACS change. Operator sets static target via Matisse Commander GUI. |
| **C — per-shot** | New `set_counterdrift_setpoint()` path in HF_Locking that talks to a custom plug-in's TCP listener. Plug-in does the actual VI manipulation. ~LV-side fragility. |
| **A** | `PROGRAM_VALUE` → `SetDeviationReference`. HF_Locking handler likely already supports this — needs verification. |
| **G** | New BLACS method `goto_wavelength(target_freq_GHz)` calling either the Network DLL (G.1), a custom plug-in's TCP listener (G.2), or a Python Network Server client (G.3). Blocking until completion. |
| **L** | Similar to G via a custom plug-in (Path G.2 equivalent), but calls `MCP LocalGoTo Set Laser To.vi` instead of the full-GoTo VI. |

Code work for these is **out of scope for this doc** — belongs in a
follow-up session with `blacs-expert` review and the GUI-local
`pid-persistence` agent at `GUIs/HF_Locking/.claude/agents/`.
