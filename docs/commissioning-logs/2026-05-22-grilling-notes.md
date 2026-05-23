# Matisse C-S external-lock grilling notes — 2026-05-22

Captured during the planning session that produced
[`matisse-c-external-locking.md`](../matisse-c-external-locking.md) and
[`matisse-external-lock-commissioning.md`](../matisse-external-lock-commissioning.md).
Purpose: preserve the operator-confirmed failure mechanism + tried-and-failed
fixes so future-Claude doesn't repeat my wrong hypotheses.

## Context

Operator goal: stop the laser lock breaking during BLACS scans.

Original framing in the previously-committed reference doc (rev 1, commit
`aca9b13`): pick between Path A (DSP External Input bypass) and Path B
(External PID plug-in). That framing was **wrong** — both paths assumed an
architecture the lab wasn't using, and Counterdrift wasn't even mentioned.

Grilling rounds 1-4 surfaced:

## Architecture (operator-confirmed)

- Lab uses the **WS7's own built-in 8-channel PID DAC card** for the lock,
  not a Matisse Commander plug-in.
- HF_Locking GUI (`GUIs/HF_Locking/`) configures the WS7 PID via wlmData
  DLL and exposes setpoints + lock indicators to BLACS over ZMQ. It is the
  monitor + comms layer, not a PID loop.
- WS7 ch4 DAC outputs to **Matisse C Reference Cell external input
  (rear-panel item 13, 0..+5V)**. Cable confirmed by operator. The 0..9000 mV
  bound in `pid_config.json` is a wide safety margin; actual operating
  voltage stays under 5V.
- This is **structurally equivalent to Matisse Commander's Counterdrift
  plug-in** (ref-cell-piezo-driven PID using WS7 reading as process value).
  The current setup is "hand-rolled Counterdrift" via WS7's own PID
  instead of Sirah's plug-in.

## Application

Confirmed:
- Primary tunable Ti:Sa laser
- Multi-purpose: spectroscopy + cooling + imaging + repump
- ~1 MHz stability over seconds-to-minutes (WS7-noise-limited floor)
- Per-shot scans: sub-MHz step resolution, 5–10 MHz steps, ~500 MHz envelope,
  **arbitrary frequency order** (not just ramps)
- Continuous ramps via Matisse Commander `Scan > Scan Setup` work fine
  mechanically, but operator needs arbitrary order, not ramps

## Failure mechanism (operator-corrected on 2026-05-22)

Three wrong hypotheses ruled out during grilling (capturing here so future
readers don't repeat them):

| Wrong hypothesis | Why it's wrong (operator told us) |
|---|---|
| "Setpoint step drives ref cell too fast → Fast Piezo can't chase flank → Fast Piezo rails first" | Close but mis-ordered. The unlock is the symptom; the sequence is different. |
| "Piezo Etalon is the bottleneck — its lock-in is disturbed by ref-cell motion" | The Piezo Etalon waveform DOES look bad, but it's a **downstream effect** of Slow Piezo searching, not the cause |
| "Current setup just needs Tier-1 features added (setpoint ramping, soft-start, rail interlock)" | Operator has already tried ramping (slow servo rate, max-change-per-shot); doesn't work because architecture itself is fragile |

**Actual mechanism (operator's words, lightly paraphrased):**

> "When the setpoint moves, the ref cell comes unlocked, and then the slow
> piezo surveys down in freq until the lock re-engages or is disabled."

Reconstructed sequence:

1. BLACS step-changes WS7 setpoint via `SetPIDCourseNum` (no ramping)
2. WS7 PID immediately drives ref-cell DAC voltage in response
3. **Internal ref-cell lock breaks** — `FASTPIEZO:LOCK?` → FALSE
   - Likely cause: Fast Piezo can't track the new ref-cell flank position
     fast enough, swings past 5%/95% range threshold (the
     `FASTPIEZO:LOCK?` criterion per Matisse Programmer's Guide p.68)
4. Slow Piezo enters `SLOWPIEZO:FREESPEED` search mode — sweeps in one
   direction looking for a ref-cell flank to re-lock to
5. Cavity length changes during sweep → Piezo Etalon waveform shakes
   (this is downstream effect, NOT cause)
6. Either re-locks (possibly on a different mode → wrong frequency) or
   operator disables

## Tried-and-failed fixes (operator-confirmed)

| Tried | Result |
|---|---|
| Reduced WS7 PID I gain (slowed servo rate) | Scans too slow to be experimentally useful |
| Capped `cmiDeviationMaxChangePerShot` | Didn't help — multi-cycle integral accumulation still moves ref cell enough to break lock |
| Tuned to close frequencies (small steps) | Didn't help — any step large enough to be useful still breaks lock |
| Continuous ramps via Matisse Commander `Scan > Scan Setup` | Works mechanically, but experiment requires arbitrary order, not ramps |

## Operator-confirmed scope of remaining work

- Bare ref-cell-only lock (WS7 servo OFF) drifts significantly over 10–60 min
  → external servo is **required**, not optional
- 500 MHz scan envelope fits comfortably within ref-cell piezo range (<30%)
  → not a rail-hitting problem
- All 4 failure modes operator listed reduce to the one root cause above —
  ref-cell lock fragility to step changes; the "idle Piezo Etalon goes
  unhappy" failure is a separate concern (Matisse internal) that's out of
  scope for the external-lock investigation

## What the grilling determined

Not solvable by adding features to the existing architecture (Counterdrift
or otherwise) because the architecture itself — **internal ref-cell lock
as inner loop driven by an outer servo on the ref-cell piezo** — is the
fragility source. To beat it we need to either:

1. Switch to an architecture without the internal ref-cell lock as inner
   loop (Candidate A — DSP External Input bypass), or
2. Add a Sirah-style coordinated retune for each frequency hop
   (Candidate G — GoTo plug-in overlay)

Both will be tested in parallel against the current setup (W) and Sirah's
own ref-cell-driven PID (C — Counterdrift) for completeness.

## Index of where this lives now

- Architecture descriptions, configs, failure mechanism →
  [matisse-c-external-locking.md](../matisse-c-external-locking.md)
- Step-by-step lab procedure to test all 4 candidates →
  [matisse-external-lock-commissioning.md](../matisse-external-lock-commissioning.md)
- This file: the trail of how we got here (for posterity)

## Lessons for future Claude

1. **Always ask what cable physically plugs into where before recommending
   anything.** I spent 3 grilling rounds with wrong architecture
   assumptions before confirming the cable goes to Reference Cell external
   input (item 13).
2. **"Lock breaks" is ambiguous.** Always ask what specifically goes FALSE
   first — `FASTPIEZO:LOCK?`, a piezo position, a frequency reading, a
   waveform display? Different first-failures point to different
   architectures.
3. **Don't assume the operator's verb is the cause.** "Piezo Etalon looks
   bad" sounds like the cause but turned out to be a downstream
   consequence of Slow Piezo search mode.
4. **"We tried X" with a vague description hides whether X actually
   addresses the right problem.** Always ask what specifically was changed,
   what the resulting symptom was, and whether the test isolated the
   intended variable.
5. **Test in parallel, don't pre-select a winner**, when the operator has
   tried multiple fixes and isn't sure which architecture works. The
   grilling here ended with the operator explicitly asking for parallel
   investigation rather than my pre-picked Path A recommendation.
