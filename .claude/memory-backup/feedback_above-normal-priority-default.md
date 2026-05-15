---
name: ABOVE_NORMAL is the right priority default for continuous-polling Python tools
description: HIGH_PRIORITY_CLASS is reserved by Microsoft for brief time-critical events; sustained HIGH on a polling loop risks starving system threads. ABOVE_NORMAL is the right default in this lab.
type: feedback
originSessionId: 9db9ac08-3097-4f43-8ecb-8652d9dbc29a
---
For continuous-polling Python tools in this lab (wavemeter GUI, BLACS workers, etc.), the correct default is `ABOVE_NORMAL_PRIORITY_CLASS` (`0x00008000`, base priority 10), NOT `HIGH_PRIORITY_CLASS` (`0x00000080`, base priority 13).

**Why:** Microsoft's [Scheduling Priorities](https://learn.microsoft.com/en-us/windows/win32/procthread/scheduling-priorities) doc is explicit: "The high-priority class should be reserved for threads that must respond to time-critical *events*." A 20 ms polling loop is sustained work, not a brief event. Sustained HIGH (base 13) outranks system threads at base 8-12 (disk flushers, USB drivers, audio) and risks starving them. ABOVE_NORMAL (base 10) sits comfortably above NORMAL and the foreground-priority boost (which only affects NORMAL-class processes anyway) without crowding the kernel. Confirmed during 2026-05-05 wavemeter session.

**How to apply:**
- Default to `SetPriorityClass(handle, 0x00008000)` for any continuous-polling Python lab tool. No admin required.
- Skip the HIGH-with-fallback dance — just use ABOVE_NORMAL directly.
- NEVER use `REALTIME_PRIORITY_CLASS` — HighFinesse manual explicitly warns of deadlock if WLM crashes in measurement mode at REALTIME, and Microsoft's general guidance is the same: REALTIME interrupts mouse/keyboard/disk system threads.
- The "HIGH requires admin, fall back to ABOVE_NORMAL" pattern in older code is misleading — ABOVE_NORMAL was the right answer all along.
