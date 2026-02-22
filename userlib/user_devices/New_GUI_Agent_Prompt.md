# BLACS Integration Section — Template for New External GUI Agents

Copy the section below into your new agent's `.claude/agents/{name}.md` file, after the hardware/scientific context section. Fill in the bracketed placeholders.

---

## BLACS Integration

This program is integrated into the BLACS experiment control system (labscript-suite at `C:\Users\radmo\labscript-suite`).

**Read `C:\Users\radmo\labscript-suite\userlib\user_devices\BLACS_COMMUNICATION_CONTRACT.md` for the full communication protocol** — it defines the ZMQ JSON format (REQ-REP + PUB-SUB), connection naming conventions, and BLACS shot lifecycle.

- **BLACS device code**: `C:\Users\radmo\labscript-suite\userlib\user_devices\{DeviceName}\`
- **Connection table**: `C:\Users\radmo\labscript-suite\userlib\labscriptlib\Main_Experiment\connection_table.py`

**Shared connection names** (must match both this server and the BLACS device — do NOT rename without updating both sides):
- `{connection_1}` — {description}
- `{connection_2}` — {description}
- `{connection_1}_monitor` / `{connection_2}_monitor` — read-only monitors

**If modifying the ZMQ protocol** (connection names, message format, PUB-SUB topics), the BLACS device must also be updated. For BLACS architecture questions (state machines, Qt thread safety), defer to the `blacs-expert` agent. For device class scaffolding (workers, tabs, register_classes), defer to the `device-builder` agent. Both live in `C:\Users\radmo\labscript-suite\.claude\agents\`.
