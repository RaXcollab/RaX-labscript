# Session Conduct Rules

## Permission denials
- **On the FIRST permission denial in a session: stop that line of work.** Do NOT retry the same action, do NOT reroute through another tool (MCP/`ctx_*`) to accomplish the denied thing, do NOT tell subagents to "retry"
- **Assume the mode is systemic** (don't-ask / sandbox), not transient. Surface it in one message — quote the denial, name what you need, let the user decide
- A second denial of the same class is proof, not noise

## Failing commands
- **Two-strike rule:** a command that fails twice with the same error is never re-issued — change tool or strategy and state the new hypothesis
- **Windows-native work goes to the PowerShell tool** (`taskkill`, `$var` expansion, `Remove-Item`). The Bash tool is MSYS: it rewrites `/F`→`F:/` and eats `$vars` in double quotes
- Never build a process-search pattern that contains its own script name — it matches itself

## Diagnosis order
- **Before opening a new investigation, check in-band sources first:** (1) this session's own tool outputs (hook errors, tracebacks already printed), (2) auto-memory / MEMORY.md, (3) prior-session notes for the same symptom. State what you found — or "nothing in-band" — before spawning searches or subagents

## Subagent output
- **Independently confirm any `UNVERIFIED` or source-less factual claim from a subagent before presenting or acting on it** — research agents have fabricated config keys and doc URLs with confident citations
- **Named background agents may idle WITHOUT delivering their report** — end every spawn prompt with "SendMessage your report to main as your final action"; idle ping with no report → nudge via SendMessage, never relaunch

## AskUserQuestion
- **Options must be plain-English and independently decidable** — no git jargon ("force-push", "fast-forward"), one decision per question, never ask what you can verify yourself first
- If an option needs a caveat to be safe, it is too complex — reframe as yes/no with the risk stated in one clause
