# Claude Code Config Knobs — Opus 4.7 → 4.8 (through v2.1.161)

**Date:** 2026-06-03
**Installed CC version:** 2.1.161 (Opus 4.8 launched in v2.1.154 on 2026-05-28)
**Scope:** env vars + settings.json + global config + CLI flags + slash commands + hooks + permissions + experimental/undocumented, from the Opus 4.7 launch through today.
**Method:** deep-research workflow (103 agents, 3-vote adversarial verification, 25/25 claims confirmed) + `claude-code-guide` agent + direct fetch of official docs/CHANGELOG + your actual settings files as ground truth.

## Confidence legend
- ✅ **Official docs** (code.claude.com / platform.claude.com / anthropic.com)
- 📋 **Official CHANGELOG / GitHub release** (anthropics/claude-code)
- 🌐 **Community-sourced** (gist / blog) — plausible, verify before relying
- ❓ **Unverified / likely wrong** — flagged so we don't ship misinformation
- 🟢 **You already have this set**

---

## 0. TL;DR — the headline changes

1. **Reasoning effort is now a first-class scale** (`low/medium/high/xhigh/max/ultracode`). Opus 4.8 defaults to `high`. You already pin `xhigh` two ways (env + settings). ✅🟢
2. **Opus 4.8 = 1M context by default** on the API. You use `model: "opus[1m]"`. Disable fleet-wide with `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`. ✅🟢
3. **Fast mode** (`/fast`, 2.5× speed, 2× price) — toggle only, **no settings.json key**. Hard-disable via `CLAUDE_CODE_DISABLE_FAST_MODE`. ✅
4. **Dynamic workflows** (`/workflows`, hundreds of parallel subagents) shipped in v2.1.154; activated via the `ultracode` effort tier. ✅
5. **Adaptive thinking is mandatory on Opus 4.7+** — `MAX_THINKING_TOKENS` / `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING` no longer apply to 4.7/4.8 (only 4.6/Sonnet 4.6). ✅
6. **Hooks exploded**: ~27 events + 4 handler types (command/http/prompt/agent). ✅📋
7. **Permission `auto` mode + `autoMode` classifier block**; since v2.1.142 `auto` is ignored in project/local settings (must live in `~/.claude.json`/user scope). You use `defaultMode: "auto"` correctly in user scope. ✅🟢
8. **⚠️ Cleanup:** your `CLAUDE_CODE_REPL: "true"` is a **dead no-op** — that env var was removed in v2.1.97. REPL/sandbox is now standard. 🌐

---

## 1. Your current config snapshot

From `~/.claude/settings.json`:
| Key | Your value | Status |
|---|---|---|
| `env.CLAUDE_CODE_REPL` | `"true"` | ❓ **REMOVED v2.1.97 — inert. Delete it.** |
| `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `"1"` | 🌐 real experimental flag (agent teams) |
| `env.CLAUDE_CODE_FORK_SUBAGENT` | `"1"` | 📋 official (CHANGELOG v2.1.117) |
| `env.CLAUDE_CODE_EFFORT_LEVEL` | `"xhigh"` | ✅ valid; **overrides** session `/effort` |
| `env.SUPERPOWERS_CONTEXT_LIMIT` | `"1000000"` | 🌐 superpowers plugin var (not core CC) |
| `model` | `"opus[1m]"` | ✅ 1M context alias |
| `effortLevel` | `"xhigh"` | ✅ valid (redundant w/ the env var, which wins) |
| `permissions.defaultMode` | `"auto"` | ✅ correctly in user scope |
| `permissions.additionalDirectories` | 1 path | ✅ |
| `statusLine` | command type | ✅ |
| `autoUpdatesChannel` | `"latest"` | ✅ (gist lists `stable`/`beta`; `latest` accepted) |
| `remoteControlAtStartup` | `true` | ❓ real key (remote/background sessions); not in fetched docs |
| `agentPushNotifEnabled` | `true` | ❓ real key (push notifs); not in fetched docs |
| `skipAutoPermissionPrompt` | `true` | ❓ real key (auto-mode); not in fetched docs |
| `enabledPlugins`, `extraKnownMarketplaces` | … | ✅ |

Project `.claude/settings.json` has a large `permissions.allow`, `additionalDirectories`, and two hooks (PreToolUse Bash safety-gate; Notification Windows MessageBox). All current and valid.

**Redundancy note:** `CLAUDE_CODE_EFFORT_LEVEL=xhigh` (env) takes precedence over `effortLevel=xhigh` (settings). Keeping both is harmless but the env var also *blocks* in-session `/effort` changes (you'll see "Not applied: …overrides effort this session"). If you ever want to flip effort per-session, drop the env var and keep only `effortLevel`.

---

## 2. Environment variables (new/changed in window)

| Variable | What it does | Default | Since | Conf |
|---|---|---|---|---|
| `CLAUDE_CODE_EFFORT_LEVEL` | Global effort: `low/medium/high/xhigh/max` or `auto`. **Immutable per-session override** — blocks `/effort`. | model default | 4.7 era | ✅ |
| `CLAUDE_CODE_DISABLE_1M_CONTEXT` | `1` = disable 1M context; removes 1M variants from model picker (enterprise/compliance). | off | 📋 CHANGELOG | 📋 |
| `CLAUDE_CODE_DISABLE_THINKING` | `1` = force-disable extended thinking regardless of model/other settings. "More direct than `MAX_THINKING_TOKENS=0`." | off | 4.7 era | ✅ |
| `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING` | `1` = revert to fixed `MAX_THINKING_TOKENS` budget. **Only affects Opus 4.6 / Sonnet 4.6; no effect on 4.7+.** | off | 4.7 | ✅ |
| `MAX_THINKING_TOKENS` | `0` disables thinking; other values only apply under fixed-budget mode (4.6/Sonnet 4.6). | unset | pre-existing, semantics changed | ✅ |
| `CLAUDE_CODE_FORK_SUBAGENT` | `1` = enable forked subagents (Agent "fork yourself") on external builds. | off | 📋 v2.1.117 | 📋 🟢 |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `1` = enable experimental agent teams (TeamCreate/SendMessage). | off | 🌐 | 🌐 🟢 |
| `CLAUDE_CODE_DISABLE_FAST_MODE` | Hard-disable fast mode. | off | fast-mode era | 🌐 |
| `CLAUDE_CODE_OPUS_4_6_FAST_MODE_OVERRIDE` | Pinned fast mode to Opus 4.6. **Deprecated, removal ~2026-06-01** → likely gone now. Use `/model claude-opus-4-6[1m]` + `/fast on`. | off | 📋 deprecated v2.1.154 | 📋 |
| `CLAUDE_CODE_DISABLE_CRON` | Disable scheduled triggers (CronCreate/RemoteTrigger). | off | 🌐 | 🌐 |
| `CLAUDE_CODE_BRIEF` | "Brief-mode permission (Kairos)". | off | 🌐 | 🌐 |
| `CLAUDE_CODE_ENABLE_CFC` | "CFC feature" (purpose unconfirmed). | off | 🌐 | 🌐 |
| `CLAUDE_CODE_SANDBOXED` | Mark session sandboxed/trusted (bypasses trust dialog). | off | 🌐 v2.1.94 | 🌐 |
| `CLAUDE_CODE_SCRIPT_CAPS` | JSON per-command Bash caps, e.g. `{"curl":3}`. | unset | 🌐 v2.1.98 | 🌐 |
| `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` | Scrub sensitive env from subprocesses. | off | 🌐 | 🌐 |
| `CLAUDE_CODE_PERFORCE_MODE` | Perforce/Helix workspace mode. | off | 🌐 v2.1.98 | 🌐 |
| `CLAUDE_CODE_AUTO_CONNECT_IDE` | Overrides `autoConnectIde` setting. | — | ✅ | ✅ |
| `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` | Skip auto-install of IDE extension. | — | ✅ | ✅ |
| `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` | Pin model IDs for Bedrock/Vertex/Foundry/AWS. `_NAME`/`_DESCRIPTION` companions set display/capabilities. | alias→latest | ✅ | ✅ |
| `CLAUDE_CODE_PLUGIN_PREFER_HTTPS` | Clone GitHub plugins over HTTPS (no SSH key). | false | 📋 (claude-code-guide) | 📋❓ |
| `ANTHROPIC_WORKSPACE_ID` | Scope minted token to a workspace (workload identity federation). | unset | 📋 (claude-code-guide) | 📋❓ |
| `ANTHROPIC_BEDROCK_SERVICE_TIER` | Bedrock service tier (`default/flex/priority`). | default | 📋 (claude-code-guide) | 📋❓ |

**REMOVED (do not use):** `CLAUDE_CODE_REPL` / `CLAUDE_REPL_MODE` (removed v2.1.97 🌐), `CLAUDE_CODE_SAVE_HOOK_ADDITIONAL_CONTEXT` (v2.1.97), `CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK` (v2.1.90), `CLAUDE_CODE_MCP_INSTR_DELTA` (v2.1.91).

---

## 3. settings.json keys (new/changed in window)

| Key | What it does | Conf |
|---|---|---|
| `model` | Model alias/ID; append `[1m]` for 1M context (stripped before send; only on supported models). | ✅ |
| `effortLevel` | `low/medium/high/xhigh`. **`max` & `ultracode` are session-only — schema error if set here.** | ✅ |
| `availableModels` | Allowlist of selectable model aliases. | ✅ |
| `permissions.defaultMode` | `default/acceptEdits/plan/auto/dontAsk/bypassPermissions`. `auto` ignored in project/local since v2.1.142. | ✅ |
| `permissions.{allow,ask,deny,additionalDirectories}` | Rule arrays + extra working dirs (config not discovered from them). | ✅ |
| `autoMode` | Auto-mode classifier: `environment/allow/soft_deny/hard_deny` prose-rule arrays; literal `"$defaults"` inherits built-ins; `hard_deny` wins. | ✅ |
| `worktree.baseRef` | `"fresh"` (default, from `origin/<default>`) or `"head"` (from local HEAD). | ✅ |
| `worktree.bgIsolation` | Background-session isolation: **`"worktree"` (default)** blocks Edit/Write in main checkout until `EnterWorktree`; `"none"` allows direct edits. *(claude-code-guide said default `auto` — wrong.)* | ✅ |
| `worktree.symlinkDirectories` | Dirs to symlink into each worktree (e.g. `node_modules`). | ✅ |
| `worktree.sparsePaths` | Sparse-checkout dirs for large monorepos. | ✅ |
| `statusLine.{type,command}` | Custom status line (`type:"command"`). | ✅ 🟢 |
| `outputStyle` | Output rendering style. *(claude-code-guide's `Verbose`/`Concise` values unconfirmed.)* | ✅ (values ❓) |
| `alwaysThinkingEnabled` | Extended thinking on by default; toggle via `/config`. (Has had persistence-regression bugs.) | ✅ |
| `showThinkingSummaries` | `true` exposes full reasoning summaries (Anthropic API interactive). | ✅/🌐 |
| `autoUpdatesChannel` | Update channel. | ✅ 🟢 |
| `enabledPlugins` / `extraKnownMarketplaces` | Plugin enablement + marketplace sources. | ✅ 🟢 |
| `env` / `hooks` | Inject env vars / wire hooks (see §6). | ✅ 🟢 |
| `showTurnDuration`, `showClearContextOnPlanAccept`, `prefersReducedMotion`, `viewMode`, `theme`, `spinnerTipsEnabled`, `spinnerTipsOverride`, `spinnerVerbs`, `terminalProgressBarEnabled` | UI/display knobs (some moved out of `~/.claude.json` at v2.1.119). | 🌐 |
| `fastMode` | **❓ NOT a real key.** Fast mode is `/fast` toggle + `CLAUDE_CODE_DISABLE_FAST_MODE` only. | ❓ |
| `remoteControlAtStartup`, `agentPushNotifEnabled`, `skipAutoPermissionPrompt` | Real keys CC accepts (in your config); not in fetched docs — confirm in `/config`. | ❓🟢 |

---

## 4. Global config — `~/.claude.json` (NOT settings.json)

These live in `~/.claude.json`; **putting them in settings.json triggers a schema validation error.**

| Key | What it does | Conf |
|---|---|---|
| `autoConnectIde` | Auto-connect to running IDE from external terminal (default `false`). Env override: `CLAUDE_CODE_AUTO_CONNECT_IDE`. | ✅ |
| `autoInstallIdeExtension` | Auto-install IDE extension from VS Code terminal (default `true`). | ✅ |
| `externalEditorContext` | Prepend prior response as commented context in external editor (Ctrl+G). | ✅ |
| `teammateDefaultModel` | Default model for agent-team teammates (`"sonnet"` default, or `null` to inherit lead's `/model`). | ✅ |
| `teammateMode` | Agent-teams mode toggle (pre-v2.1.119 stored here). | ✅ |
| `autoScrollEnabled`, `editorMode`, `showTurnDuration`, `terminalProgressBarEnabled` | Pre-v2.1.119 stored here, now in settings.json. | ✅ |

---

## 5. CLI flags & subcommands (new in window)

| Item | What it does | Conf |
|---|---|---|
| `claude agents` | Open agent view; monitor/dispatch parallel background sessions. `--cwd`, `--json`. | ✅ |
| `claude agents --add-dir/--settings/--mcp-config/--plugin-dir/--permission-mode/--model/--effort/--dangerously-skip-permissions` | Configure dispatched background sessions. | 📋 |
| `claude attach <id>` | Attach to a background session in this terminal. | ✅ |
| `claude auto-mode defaults` / `auto-mode config` | Print built-in auto-mode classifier rules / effective config as JSON. | ✅ |
| `claude daemon status` | Background-session supervisor status. | ✅ |
| `claude install [version\|stable\|latest]` | Install/reinstall native binary at a version. | ✅ |
| `claude auth login/logout/status` | Account auth (`--console`, `--sso`, `--email`, `--text`). | ✅ |
| `--effort <level>` | Per-session effort at launch. | ✅ |
| `--permission-mode <mode>` | Override `defaultMode` for the session (incl. `auto`). | ✅ |
| `--worktree`, `--add-dir`, `--agent`, `--settings`, `--mcp-config`, `--plugin-dir` | Worktree isolation / extra dirs / agent persona / config injection. | ✅ |

---

## 6. Slash commands (new/changed in window)

| Command | What it does | Conf |
|---|---|---|
| `/fast` | Toggle fast mode (Opus 4.6/4.7/4.8; requires v2.1.36+). | ✅ |
| `/effort [level\|auto]` | Set effort; bare opens slider; also in `/model` via arrows. | ✅ |
| `/workflows` | View dynamic-workflow runs (v2.1.154). | ✅ |
| `/context` | Context-window usage + actionable suggestions. | ✅ |
| `/usage` | Token/cost/plan usage; `/cost` & `/stats` are typing shortcuts into its tabs (v2.1.118+); per-category limits v2.1.149+. | ✅/🌐 |
| `/rewind` | Return to a checkpoint (or `Esc` twice). | 🌐 |
| `/loop [interval] <cmd>` | Recurring task, e.g. `/loop 5m /foo`; omit interval = self-paced. (Bundled skill.) | ✅ |
| `/plan` | Enter plan mode. | 🌐 |
| `/powerup` | Interactive feature lessons (v2.1.90+). | 🌐 |
| `/voice` | Push-to-talk voice mode. | 🌐 |
| `/run`, `/verify`, `/run-skill-generator` | Launch/verify your app against the running build (v2.1.145+, bundled skills). | ✅ |
| `/batch`, `/debug`, `/code-review`, `/claude-api` | Bundled prompt-based skills. | ✅ |

Note: **custom commands merged into skills** — `.claude/commands/x.md` and `.claude/skills/x/SKILL.md` both create `/x`.

---

## 7. Hooks (new in window)

**Handler types (4):** `command` (shell), `http` (POST to endpoint, Feb 2026), `prompt` (LLM hook, default 30s timeout), `agent` (spawns a subagent with Read/Grep/Glob, ≤50 turns, returns `{"ok":true/false}`, default 60s timeout). Plus **async/non-blocking hooks** (Jan 2026). ✅📋

**Config shape:**
```json
{ "hooks": { "PreToolUse": [ { "matcher": "Edit|Write",
  "hooks": [ { "type": "command", "command": "~/.claude/hooks/gate.sh" } ] } ] } }
```

**Event catalog expanded to ~27** (count is 🌐; individual events ✅). Classic set: `SessionStart, SessionEnd, UserPromptSubmit, PreToolUse, PostToolUse, Stop, SubagentStop, Notification, PreCompact`. New: `Setup, UserPromptExpansion, PostToolUseFailure, PostToolBatch, PermissionRequest, PermissionDenied, SubagentStart, TaskCreated, TaskCompleted, TeammateIdle, PostCompact, StopFailure, ConfigChange, InstructionsLoaded, CwdChanged, FileChanged, WorktreeCreate, WorktreeRemove, MessageDisplay, Elicitation, ElicitationResult`.

**v2.1.152 additions:** `MessageDisplay` hook (transform/hide assistant text as displayed); `SessionStart` can return `reloadSkills:true` (re-scan skill dirs same-session) and set session title via `hookSpecificOutput.sessionTitle`; skills/slash commands can set `disallowed-tools` in frontmatter. ✅📋

---

## 8. Permissions / auto-mode

- **`defaultMode` gained `auto`** (in addition to `default/acceptEdits/plan/dontAsk/bypassPermissions`). ✅
- **v2.1.142 security change:** `auto` is **ignored** in project/local settings — a repo can't grant itself auto mode; set in `~/.claude.json`/user scope (you do this correctly). `--permission-mode` CLI flag overrides per session. ✅
- **`autoMode` classifier block:** `environment`, `allow`, `soft_deny`, `hard_deny` arrays of **natural-language prose rules**; `"$defaults"` inherits built-ins at that position; `hard_deny` cannot be overridden. Inspect with `claude auto-mode defaults`. ✅
- Permission rules **merge across scopes** (don't override like other settings). ✅

---

## 9. Opus 4.8 model-specific

| Feature | Detail | Conf |
|---|---|---|
| Default effort | `high` on all surfaces (API + Claude Code). | ✅ |
| 1M context | Default on API/Bedrock/Vertex (200k on Foundry); 128k max output. Max/Team/Enterprise auto-upgrade Opus to 1M, no config. Disable: `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`. | ✅ |
| `[1m]` suffix | `opus[1m]`/`sonnet[1m]`; stripped before send; per-variable on 3rd-party providers. | ✅ |
| Fast mode | API `speed:"fast"` (beta header `fast-mode-2026-02-01`) / `/fast`. 2.5× speed, $10/$50 per MTok (2× standard; 3× cheaper than on 4.7/4.6). | ✅ |
| Dynamic workflows | v2.1.154; Claude writes orchestration scripts → tens–hundreds of parallel subagents; `/workflows` to view; `ultracode` activates. Max/Team/Enterprise (Enterprise off by default). ~16 concurrent/~1000 total cap (🌐). | ✅ |
| Model alias resolution | API: `opus`→4.8, `sonnet`→4.6. Claude Platform on AWS: `opus`→4.7. Bedrock/Vertex/Foundry: `opus`→4.6, `sonnet`→4.5. (June 2026 snapshot.) | ✅ |
| v2.1.154 misc | `/effort` slider relabeled Speed/Intelligence → **Faster/Smarter**; CC rate limits raised for higher-effort token usage. | 📋 |

---

## 10. Highest-impact shortlist for you

1. **Delete `env.CLAUDE_CODE_REPL`** — dead since v2.1.97; it's clutter that implies a behavior that no longer exists.
2. **Decide effort source of truth** — env var `CLAUDE_CODE_EFFORT_LEVEL=xhigh` blocks `/effort`. If you want per-session flexibility, drop it and keep only `effortLevel`. If you want it locked, keep the env var and drop the redundant settings key.
3. **`CLAUDE_CODE_DISABLE_1M_CONTEXT`** — know it exists; only if a session's 1M context ever causes cost/latency surprises on the lab box.
4. **`autoMode` classifier block** — you run `defaultMode:"auto"` + `skipAutoPermissionPrompt`. Author explicit `hard_deny` prose rules (e.g. "never push to backend repos", "never `rm -r`") to harden auto mode beyond the Bash PreToolUse hook you already have.
5. **`worktree.bgIsolation` / `--worktree`** — you already use `.claude/worktrees/`; setting `baseRef:"head"` may suit your topic-branch workflow (matches your "destabilizing work → topic branch" rule).
6. **Agent hooks (`type:"agent"`)** — your Bash safety-gate is a brittle shell regex; an agent hook could make smarter allow/deny calls (e.g. "is this git push targeting a backend repo?").
7. **Dynamic workflows / `ultracode`** — you already lean on multi-agent orchestration; `ultracode` makes it the default for substantive tasks.
8. **`CLAUDE_CODE_DISABLE_CRON` awareness** — you have scheduled-trigger tooling; know the kill switch exists.

---

## 11. Cleanup / action items
- [ ] Remove dead `CLAUDE_CODE_REPL` from `~/.claude/settings.json`.
- [ ] Resolve `CLAUDE_CODE_EFFORT_LEVEL` vs `effortLevel` redundancy (pick one).
- [ ] Confirm `remoteControlAtStartup` / `agentPushNotifEnabled` / `skipAutoPermissionPrompt` against `/config` (real keys, but not in fetched docs).
- [ ] Verify `CLAUDE_CODE_OPUS_4_6_FAST_MODE_OVERRIDE` is gone (scheduled removal ~2026-06-01) if referenced anywhere.
- [ ] Consider authoring an `autoMode` block now that you run `defaultMode:"auto"`.

## 12. Items still ❓ (verify before relying)
- `fastMode` settings key (likely not real — use `/fast`).
- `outputStyle` value set (`Verbose`/`Concise` unconfirmed).
- `CLAUDE_CODE_PLUGIN_PREFER_HTTPS`, `ANTHROPIC_WORKSPACE_ID`, `ANTHROPIC_BEDROCK_SERVICE_TIER` (changelog-claimed by claude-code-guide, not independently re-verified here).
- `CLAUDE_CODE_BRIEF`, `CLAUDE_CODE_ENABLE_CFC` (purpose unconfirmed, community gist only).
- The exact "27" hook-event count (community); individual events are doc-confirmed.

## Sources
- code.claude.com/docs/en/{settings, env-vars, model-config, fast-mode, hooks, cli-reference, slash-commands, permission-modes, auto-mode-config, workflows, agent-view}
- platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-8 ; .../build-with-claude/{effort, fast-mode}
- github.com/anthropics/claude-code: CHANGELOG.md, releases/tag/v2.1.154 (28 May 2026, commit 1696f22), v2.1.117 (`CLAUDE_CODE_FORK_SUBAGENT`), v2.1.152
- anthropic.com/news/claude-opus-4-8 ; anthropic.com/engineering/claude-code-auto-mode
- Community (🌐): Claude Code env-vars gist (mculp), Blake Crosley Cheat Sheet 2026, claudefa.st hooks guide, yaw.sh settings reference, claudelog.com
