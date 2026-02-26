---
name: debug-blacs
description: Standardized BLACS triage workflow for crashes, errors, and unexpected behavior
disable-model-invocation: true
---

Run the BLACS triage workflow. User-reported issue: $ARGUMENTS

## Triage Steps (execute in order)

### 1. Check faulthandler log (segfaults)
Read `logs/BLACS_faulthandler.log` — if the file has recent entries, this was a C-level crash.
- Look for Qt widget calls from non-GUI threads (most common cause)
- Check thread IDs to identify which thread crashed
- If found: this is likely a `qtlock` vs `inmain()` issue. Route to `blacs-expert`.

### 2. Check BLACS.log (Python errors)
Read the last 200 lines of `logs/BLACS.log`.
- Look for Python tracebacks, ERROR-level entries, and WARNING patterns
- Note timestamps relative to shot execution
- Classify errors using the diagnostics agent categories

### 3. Check connection table state
Read `userlib/labscriptlib/Main_Experiment/connection_table.py`.
- Verify device names and ports match the External GUI Registry
- Check for recent changes (git diff)

### 4. Check external GUI status
For RemoteControl devices, verify the external GUIs are running.
- Use `/check-guis` if available, or manually check ZMQ ports

### 5. Route to specialist
Based on findings:
- **Segfault / thread safety** → `blacs-expert`
- **Log pattern analysis** → `labscript-diagnostics`
- **Device class issue** → `device-builder`
- **Connection table issue** → `amo-expert`
- **Analysis pipeline issue** → `lyse-analysis`

### 6. Report
Summarize findings with:
- Error classification (critical / warning / informational)
- Root cause (confirmed or suspected)
- Recommended fix
- Whether this is a recurring issue (check diagnostics agent memory)
