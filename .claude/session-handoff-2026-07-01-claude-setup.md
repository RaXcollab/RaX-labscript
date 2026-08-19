# Claude Code Setup — Machine Handoff Report

**Machine:** `RaX-Control` · **Date:** 2026-07-01 · **User:** arianjad@mit.edu (git: RaX-1 / RadMolecules)
**Purpose:** Complete snapshot of the Claude Code configuration on this PC, for handoff to a fresh session.

---

## 0. TL;DR / Orientation

- **The Claude config is version-controlled *inside the labscript-suite repo* (`.claude/`), not in a `~/.claude` dotfiles repo.** That project-scoped `.claude/` IS the "home config" — 43 files tracked on `RaXcollab/RaX-labscript`.
- `~/.claude` (the global user dir) holds behavior-shaping `settings.json`, the plugin cache, and the native auto-memory — all **machine-local, not in any git repo**.
- **Two independent memory systems run at once:** native auto-memory (`MEMORY.md` + files) and the `claude-mem` plugin (worker + chroma vector DB).
- **⚠️ Safety hooks are currently DISABLED** — `settings.local.json` sets `"disableAllHooks": true`, which turns off the `rm -rf`/backend-push guard hook defined in `settings.json`. See §4.5.
- **⚠️ claude-mem worker is wedged** — PID 26172 holds port 37777 (LISTENING) but `/api/health` returns ECONNREFUSED. Needs a restart.

---

## 1. Answers to the 7 diagnostic questions

**1. OS + shell**
- Windows 11 Pro for Workstations, build **10.0.26200**. Hostname `RaX-Control`.
- Shells: **MSYS2/MinGW64 bash** 3.6.6 (`/usr/bin/bash`) via the Bash tool; **PowerShell 7** is the primary interactive shell. `cmd.exe` also present.

**2. Tool versions** (none missing)
| node | bun | uv | npm | git |
|---|---|---|---|---|
| v24.13.1 | 1.3.14 | 0.11.14 | 11.8.0 | 2.53.0.windows.1 |

**3. ~/.claude** — exists. See §3 for full global `settings.json`. Marketplaces in `~/.claude/plugins/marketplaces/`: `claude-plugins-official`, `context-mode`, `thedotmack`.

**4. claude-mem** — installed. Cache versions `13.4.2`, `13.5.5`, `13.8.1`, `13.9.2` (active **13.9.2**). Health: worker PID **26172 LISTENING on 127.0.0.1:37777** per netstat, but `/api/health` on 37777 **and** 37701 → **ECONNREFUSED** (both node fetch and curl). Worker is up-but-not-serving → restart needed. NB: this is *not* the documented "unwritten .worker.pid false-negative" (that one still answers /api/health); this endpoint genuinely refuses.

**5. ~/.claude.json mcpServers keys** — top-level: **none** (`[]`). Project `C:/Users/radmo/labscript-suite`: **`keepgoing`**, **`context7`**. (Plugins add more MCP servers at runtime — see §6.)

**6. Synced home-config or fresh?** — **Synced, but project-scoped.** Config lives in `labscript-suite/.claude/` (remote `github.com/RaXcollab/RaX-labscript`). Neither `~` nor `~/.claude` is a git repo. So: config is under version control via the project repo; the global `~/.claude` layer (settings/plugins/native-memory) is unsynced/machine-local.

**7. Python/conda for DAQ** — miniconda at `C:\Users\radmo\miniconda`. 7 envs (see §8). `labscript` env: labscript 3.4.0, numpy 1.26.4, PyQt5 5.15.11, h5py 3.15.1, PyVISA 1.15.0, zprocess 2.27.0, **pyzmq 25.1.0** (⚠️ CLAUDE.md pins 23.2.0 "do not upgrade" — mismatch in this env; pin may apply to guis/hf_locking envs). blacs/labscript-devices/labscript-utils are editable installs pointing at the local repo folders. NI access is via **PyDAQmx** (referenced in permission allow-list) / the labscript-devices `NI_DAQmx` driver; the `nidaqmx` pip package did **not** appear in `labscript` env's `pip list`.

---

## 2. Config architecture — where everything lives

```
~/.claude/                                  ← GLOBAL, machine-local, NOT in git
  settings.json                             ← behavior: model, effort, env, plugins, permissions (§3)
  statusline-command.sh                     ← custom status line
  plugins/
    marketplaces/{claude-plugins-official, context-mode, thedotmack}
    cache/thedotmack/claude-mem/{13.4.2,13.5.5,13.8.1,13.9.2}
  projects/c--Users-radmo-labscript-suite/
    memory/MEMORY.md + *.md                 ← NATIVE auto-memory (§7)
~/.claude.json                              ← per-project MCP server defs (§6)

labscript-suite/.claude/                    ← PROJECT config, TRACKED in RaXcollab/RaX-labscript (§4)
  settings.json                             ← permissions + safety hooks (§4.5)
  settings.local.json                       ← local overrides — disableAllHooks:true (⚠️)
  agents/    (8 domain subagents)
  rules/     (13 path-scoped rules)
  skills/    (6 skills)
  templates/ (lab-note.html)
  docs/superpowers/  (UNTRACKED)
  agent-memory/, memory-backup/, backup-memory.sh
  session-handoff-*.md
labscript-suite/CLAUDE.md                   ← main project instructions (tracked)
labscript-suite/docs/*.md                   ← 20+ domain reference docs (tracked, §4.4)
```

---

## 3. Global `~/.claude/settings.json` (behavior-shaping)

- **`model`: `opus[1m]`** · **`effortLevel`: `xhigh`**
- **`env`:**
  - `SUPERPOWERS_CONTEXT_LIMIT=1000000`
  - `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
  - `CLAUDE_CODE_FORK_SUBAGENT=1`
  - `CLAUDE_CODE_EFFORT_LEVEL=xhigh`
- **`permissions.defaultMode`: `dontAsk`** — low-friction; combined with `skipAutoPermissionPrompt:true` and `skipDangerousModePermissionPrompt:true`.
- `additionalDirectories`: `C:\Users\radmo\.claude\plans`
- `tui: fullscreen` · `autoUpdatesChannel: latest` · `autoCompactEnabled: true` · `remoteControlAtStartup: true` · `agentPushNotifEnabled: true` · `switchModelsOnFlag: false`
- `statusLine`: `bash /c/Users/radmo/.claude/statusline-command.sh`
- Global permission allow-list is heavily seeded with web-research domains (laser/photonics/labscript), `git ls-remote *`, conda, and context-mode MCP tools.

**Net effect:** this machine runs Opus 1M at xhigh effort, agent-teams + fork-subagent enabled, minimal permission prompting. A fresh session inherits all of this.

---

## 4. Project `.claude/` config (the in-repo "home config")

### 4.1 Agents (`.claude/agents/`, 8)
`amo-expert`, `blacs-expert`, `device-builder`, `lyse-analysis`, `labscript-diagnostics`, `session-notes`, `wrap-up`, `context-auditor`.
Plus **GUI-local agents** live in `GUIs/*/.claude/agents/` (HF_Locking→pid-persistence, rastering→ablation-tech, BigSkyControl→bigsky-yag-laser-controller). Don't flag those as missing without checking the GUI folder.

### 4.2 Rules (`.claude/rules/`, 13 — path-scoped auto-load)
Behavioral: `analysis.md`, `context-writing.md`, `devices.md`, `sequences.md`.
Reference (`ref-*`): `ref-analysis`, `ref-blacs-patterns`, `ref-blacs-state-machine`, `ref-external-guis`, `ref-hf-locking-rates`, `ref-labscript-api`, `ref-main-experiment`, `ref-remotecontrol-zmq`, `ref-yag-physics`. Each maps a file-path glob → a `docs/*.md` reference doc.

### 4.3 Skills (`.claude/skills/`, 6)
`agent-workflow`, `check-guis`, `check-sequence`, `debug-blacs`, `new-device`, `revert-to-main`. (Invoke as `/check-guis` etc.)

### 4.4 Domain docs (`labscript-suite/docs/`, tracked)
20+ reference docs auto-loaded via the `ref-*` rules: `blacs-state-machine`, `blacs-device-patterns`, `remotecontrol-zmq-protocol`, `external-guis-architecture`, `main-experiment-overview`, `shot-h5-layout`, `labscript-api`, `analysis-api`, `ni-scope-conventions`, `hf-locking-rates`, `yag-laser-physics`, `matisse-c-external-locking`, `known-latent-issues`, `stable-snapshot-2026-06-09`, `context-best-practices`, `rollback-2026-05-26-revival-inventory`, + `Using_Claude_Code.html`, `changelog.html`, `PATHFINDER-2026-06-09/`.

### 4.5 Hooks & permissions (⚠️ read this)
`.claude/settings.json` **defines two hooks:**
- **PreToolUse (Bash matcher):** blocks `git push` to `blacs`/`labscript-devices`/`labscript-utils`; blocks `rm -r`/`rm -rf`; blocks `mv` on directories. Safety guard.
- **Notification:** PowerShell MessageBox popup "Claude Code needs your attention".

**BUT `.claude/settings.local.json` sets `"disableAllHooks": true`** → **both hooks are currently inactive.** A fresh session on this machine has NO `rm -rf`/backend-push guardrail from hooks; only the CLAUDE.md prose conventions apply. If you want the guard back, remove/flip that key. `settings.local.json` also carries a large allow-list of specific git tag/push/worktree commands left over from the 2026-06-09 stable-snapshot tagging session.

`settings.json` `additionalDirectories`: `.claude/skills`, the MIT Dropbox `Main_Experiment` shot-storage folder, the WindowsTerminal `LocalState`, and `.claude`.

---

## 5. Plugins & marketplaces

**Marketplaces:** `claude-plugins-official` (built-in), `context-mode`, `thedotmack` (github `thedotmack/claude-mem`).

**14 enabled plugins:** superpowers, code-review, claude-md-management, skill-creator, claude-code-setup, atlassian, hookify, greptile, frontend-design, github, context-mode, claude-mem, context7, commit-commands.

These contribute the large skill/command surface (superpowers/*, code-review, commit-commands, hookify, atlassian/*, claude-mem/*, context-mode/*, etc.).

---

## 6. MCP servers

- **Project-scoped (in `~/.claude.json` under this project):**
  - `keepgoing` → `npx -y @keepgoingdev/mcp-server` (stdio)
  - `context7` → `npx -y @upstash/context7-mcp@latest` (stdio)
- **Plugin-provided (loaded at runtime):** `claude-mem` mcp-search (`memory_search`, `observation_*`, `smart_*`, `timeline`…), `context-mode` (`ctx_*`), `context7` (also as a plugin — **duplicated** with the project MCP def above), `atlassian` (**requires OAuth — unauthenticated in headless/non-interactive sessions**).
- **Also referenced by claude.ai connectors:** Gmail, Google Calendar, Google Drive (available only when the claude.ai connector is authorized).

Note the **context7 duplication** (plugin + project MCP) — harmless but redundant; consider dropping one.

---

## 7. Memory systems (two, both live)

1. **Native auto-memory** — `~/.claude/projects/c--Users-radmo-labscript-suite/memory/`. `MEMORY.md` is the index (capped ~25k chars on load, compaction target ~17.5k). Individual `.md` files hold one fact each (type: user/feedback/project/reference). Loaded into every session's context.
2. **claude-mem plugin** — persistent cross-session DB (observations + chroma vector store), worker on **:37777** (⚠️ currently wedged, see §1.4), searchable via the mcp-search MCP tools and `/mem-search`. `smart_*` structural search is **broken on this machine** (tree-sitter runtime missing from bundle — memory/vector search unaffected; use native Read/Grep/Glob).
3. **In-repo memory dirs** — `.claude/agent-memory/`, `.claude/memory-backup/`, `.claude/backup-memory.sh` (backup tooling).

Don't conflate #1 and #2 — different stores, different tools.

---

## 8. Python / conda

miniconda: `C:\Users\radmo\miniconda`. Envs: **base, analysis, claude_debug, guis, hf_locking, labscript, rastering**.

`labscript` env key packages:
| pkg | ver | | pkg | ver |
|---|---|---|---|---|
| labscript | 3.4.0 | | numpy | 1.26.4 |
| labscript-suite | 3.3.0 | | h5py | 3.15.1 |
| labscript-utils | 3.4.0.dev28 (editable) | | PyQt5 / sip | 5.15.11 / 12.17.0 |
| labscript-devices | 3.3.0.dev57 (editable) | | pyqtgraph | 0.13.7 |
| blacs | 3.3.0.dev54 (editable) | | PyVISA | 1.15.0 |
| labscript-c-extensions | 1.2.1 | | zprocess | 2.27.0 |
| | | | **pyzmq** | **25.1.0** (⚠️ vs pinned 23.2.0) |

- Editable installs (`blacs`, `labscript-devices`, `labscript-utils`) point at the local repo subfolders → code edits are live.
- Each GUI/subsystem has its own env (`guis`, `hf_locking`, `rastering`, `analysis`). REPL must `conda activate <env>` before invoking those `python.exe` (direct invocation hangs on missing DLL paths).

---

## 9. Repo topology (multi-repo workspace)

| Dir | Remote | Role |
|---|---|---|
| `.` (labscript-suite) | `RaXcollab/RaX-labscript` (HTTPS) | User-facing; tracks `userlib/` + `.claude/` + `docs/` |
| `blacs/` | `RaXcollab/blacs` (fork of shafinulh) | Backend runtime |
| `labscript-devices/` | `RaXcollab/labscript-devices` | Backend drivers |
| `labscript-utils/` | `RaXcollab/labscript-utils` | Backend utils |
| `GUIs/HF_Locking`, `GUIs/rastering`, `GUIs/BigSkyControl`, … | separate `RaXcollab/*` repos | External GUIs |

Parent `.gitignore` excludes backend folders + `GUIs/`, `labconfig/`, `logs/`, etc. **Commit each repo separately; never push without asking.** Backend repos: **never apply non-`v*` tags** (setuptools_scm parses `git describe` at import → crashes all imports → BLACS/RunManager won't start). Pin baselines by commit hash.

GUIs present under `GUIs/`: BigSkyControl, HF_Locking, LabMonitoring, LakeshoreGUI, Microcontrollers, MKS_Flowcontroller_v2, quadmag_gui, rastering, rastering-stepping, rastering-zmq-v2, Thermocouples (+ `envs/`, `HF_Old.zip`).

External-GUI BLACS device registry (name → device path → REQ/PUB ports): Laser Lock → `LaserLockDevice` → 3796/3797; Rastering → `RasteringDevice` → 55535/55536; BigSky YAG → `BigSkyHub` → 55540/55541.

---

## 10. Action items / watch-list for the next session

1. **claude-mem worker wedged** — restart it; `/api/health` on 37777 refuses despite LISTENING socket (PID 26172).
2. **Safety hooks are OFF** (`disableAllHooks: true` in `.claude/settings.local.json`). Decide whether to re-enable the `rm -rf`/backend-push guard.
3. **pyzmq 25.1.0 in `labscript` env** vs the "do-not-upgrade 23.2.0" note — confirm whether the pin was meant for this env or only guis/hf_locking.
4. **context7 is double-registered** (plugin + project MCP) — redundant.
5. **atlassian MCP unauthenticated** in non-interactive sessions — needs `/mcp` auth in an interactive session if used.
6. **`smart_*`/tree-sitter search broken** — use native Read/Grep/Glob; memory + vector search fine.

## 11. Untracked `.claude/` items (local-only, not yet synced)
`.claude/CLAUDE.md` (claude-mem context stub), `.claude/docs/superpowers/`, `.claude/skills/check-guis/CLAUDE.md`, `.claude/skills/revert-to-main/CLAUDE.md`, `.claude/worktrees/`. None are gitignored — a plain `git add` would pick them up. Working tree is a normal "mixed" state; commit only your own files by name.

---
*Generated read-only. No settings, repos, or services were modified in producing this report.*
