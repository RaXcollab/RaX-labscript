---
name: Win11 has two independent throttling axes
description: Priority class and EcoQoS power throttling are independent — fixing one does not fix the other. Both must be addressed for latency-sensitive lab tools.
type: feedback
originSessionId: 9db9ac08-3097-4f43-8ecb-8652d9dbc29a
---
Windows 11 has TWO independent throttling axes for unfocused/background processes:

1. **Priority class** (`SetPriorityClass`) — affects scheduler preemption order
2. **EcoQoS / power throttling** — independently caps CPU clock speed and migrates to E-cores when window unfocused (Win10 1709+, much more aggressive on Win 11)

Setting `HIGH_PRIORITY_CLASS` does NOT disable EcoQoS. They are separate kernel mechanisms.

**Why:** Diagnosed during HighFinesse wavemeter GUI focus-throttling session (2026-05-05). The GUI already had `SetPriorityClass(HIGH)` but felt laggy when unfocused. Root cause was EcoQoS, not priority. Adding the priority elevation alone never fixed it.

**How to apply:**
- For latency-sensitive **Python** tools: in-process call to `kernel32.SetProcessInformation(handle, ProcessPowerThrottling=4, &state, sizeof(state))` with `Version=1, ControlMask=PROCESS_POWER_THROTTLING_EXECUTION_SPEED=0x1, StateMask=0`. Pattern lives in `GUIs/HF_Locking/main_wlm.py`.
- For **closed-source binaries** (e.g. vendor servers like `wlm_ws7.exe`): `powercfg /powerthrottling disable /path "<full exe path>"` from elevated shell. Persists in registry, survives reboots, may be wiped by major Windows feature updates.
- The per-EXE `powercfg` rule on the conda interpreter (`C:\Users\radmo\miniconda\envs\labscript\python.exe`) covers all labscript tools (BLACS, runmanager, lyse, GUIs) with one command. Wide blast radius but typically desirable for a dedicated lab PC.
