# Nanosecond Pulsed Nd:YAG Laser Reference

Reference doc for agents working on BigSky YAG integration (`user_devices/BigSkyHub/`, `GUIs/BigSkyControl/`).

## How Q-Switched Nd:YAG Lasers Work

A Q-switched Nd:YAG laser produces **nanosecond pulses** (5-15 ns) by storing energy in the gain medium, then releasing it all at once.

### Pulse Formation Sequence

```
t = 0 us         Flashlamp fires (capacitor discharge into xenon lamp)
                  Nd3+ ions pumped to upper laser level (4F3/2, lifetime ~230 us)
                  Q-switch holds cavity at LOW Q (no lasing possible)

t = 0-220 us     Flashlamp pumps rod, population inversion grows toward saturation

t ~ 140 us       Q-SWITCH OPENS (voltage drops to zero)
                  Cavity Q goes HIGH instantly
                  Stimulated emission avalanche over ~10-20 round trips

t ~ 140 us       GIANT PULSE emitted (5-15 ns FWHM, megawatt peak power)
+ 5-15 ns        Gain medium depleted
```

### Key Components

- **Flashlamp**: Xenon flashlamp pumps the Nd:YAG rod. ~90% of energy becomes heat; ~5-6% becomes laser output. Discharge lasts ~200-220 us matching the upper-state lifetime. Simmer current maintains ionization between pulses for reliability.

- **Q-switch (Pockels cell)**: KD*P electro-optic crystal + polarizer. Quarter-wave voltage (~3 kV) blocks lasing. Dropping to zero opens the cavity. Switching time ~ns.

- **Q-switch delay**: Time from flashlamp trigger to Q-switch opening. Default **140 us** on our BigSky lasers. Optimal range: 140-200 us. Too early = weak pulse; too late = energy decayed; optimal = maximum energy, minimum jitter (~0.5 us).

## Trigger Modes

### Flashlamp Trigger (`>lpm0` / `>lpm1`)

| Mode | Command | Description |
|------|---------|-------------|
| Internal (0) | `>lpm0` | Controller fires flashlamp at internally-set rep rate. Used for **warmup**. |
| External (1) | `>lpm1` | Flashlamp fires on external TTL trigger (+5V, 100 us pulse). Used for **experiment sync**. |

### Q-Switch Trigger (`>qsm0` / `>qsm1` / `>qsm2`)

| Mode | Command | Description |
|------|---------|-------------|
| Internal (0) | `>qsm0` | Controller fires Q-switch at fixed delay after flashlamp. **Our standard mode.** |
| Burst (1) | `>qsm1` | Multiple Q-switch pulses per flashlamp. Not used in our lab. |
| External (2) | `>qsm2` | Q-switch fires on separate external trigger. Requires delay generator. |

### Our Lab Configuration: Internal QS + External Lamp

The standard operating mode is **lamp_mode=1 (external) + qswitch_mode=0 (internal)**:

1. BLACS sends flashlamp trigger via PrawnBlaster digital line, synchronizing YAG pulses with the experiment
2. The BigSky controller handles the 140 us Q-switch delay internally
3. No delay generator needed; low jitter (~0.5 us); simple one-trigger-per-pulse

During **warmup**: lamp_mode=0 (internal), lamps fire freely at set rep rate with shutter closed. Q-switch stays internal and disabled.

## Operating Parameters (BigSky Ultra/CFR)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Pulse duration | 7-15 ns FWHM | Ultra: 7-9 ns; CFR: <15 ns |
| Pulse energy | 10-400 mJ @ 1064 nm | Voltage-dependent |
| Rep rate | 1-50 Hz | Max 30 Hz comfortable with external trigger |
| Q-switch delay | 140 us default | Adjustable; optimal 140-200 us |
| Flashlamp voltage | 500-1400 V | Below lasing threshold ~725 V (warmup) |
| External trigger | +5V, 100 us pulse | Pin 4 (+), Pin 9 (-) on 9-pin D-sub |
| Jitter (lamp→pulse) | ~0.5 us | With internal QS at optimal delay |
| Baud rate | 9600 (fixed) | RS-232 serial, 1s timeout |

## Warmup Process

When flashlamps fire, ~90% of energy heats the YAG rod, creating:

- **Thermal lensing**: Radial temperature gradient acts as a lens (refractive index depends on temperature). Beam quality and mode change until equilibrium.
- **Beam pointing drift**: Wanders until thermal gradient stabilizes.
- **Energy instability**: Shot-to-shot fluctuations until thermal equilibrium.

**Procedure**: Fire lamps at low voltage (below lasing threshold) with shutter closed and Q-switch off. Monitor coolant temperature:
- **Cold**: < 37 C -- do not lase
- **Warming**: 37-39 C -- approaching equilibrium
- **Operating**: >= 39 C -- stable for lasing

Warmup takes 10-20 minutes. The BLACS Keep Warm feature auto-maintains warmup between shot queues.

## Serial Command Reference

| Command | Response | Description |
|---------|----------|-------------|
| `>a` | status | Activate flashlamps |
| `>s` | status | Standby (clears all: lamps, shutter, QS) |
| `>r1` / `>r0` | status | Open / close shutter |
| `>pq` / `>sq` | status | Arm / disarm Q-switch |
| `>lpm0` / `>lpm1` | mode | Set lamp mode internal / external |
| `>qsm0/1/2` | mode | Set QS mode internal / burst / external |
| `>vmoXXX` | voltage | Set flashlamp voltage (e.g., `>vmo0870`) |
| `>v` | voltage | Query current voltage |
| `>cg` | temp | Query coolant temperature |
| `>f` / `>fXXX` | freq | Query / set rep rate (in Hz*100) |
| `>sn` | serial | Query serial number |
| `>sav1` | status | Save current settings to EEPROM |

**Response quirk**: BigSky sends `\r\n` *before* the response text. Code reads 140 bytes and strips `\r\n`.

**Mode changes require standby**: Must send `>s` before `>lpm` or `>qsm` commands.

**Safety interlocks** (enforced by hardware + software):
- Shutter requires lamps active
- Q-switch requires lamps active + shutter open
- Voltage range: 500-1400 V
