# `CLAUDE_MEM_*` env-var reference (claude-mem v13.2.0)

Source: `~/.claude/plugins/cache/thedotmack/claude-mem/13.2.0/scripts/{context-generator.cjs,worker-service.cjs}`. `V.DEFAULTS` block lives at **context-generator.cjs L693** (`var V=class{static DEFAULTS={...}}`) and **worker-service.cjs L20** (`var Pe=class{...}`). 71 keys observed at `/api/settings` (1 = `CLAUDE_CODE_PATH`, 70 = `CLAUDE_MEM_*`). Lookups go through `Pe.loadFromFile(Jt)` → file overrides `process.env[k] ?? DEFAULTS[k]`.

`process.getuid?.()??77` on Windows = 77, so `WORKER_PORT = 37777` and `SERVER_BETA_URL = http://127.0.0.1:37954`.

---

## Exhaustive settings table (by group)

### Group: Context-injection — what enters the session-start block
| Var | Default | Type | What it does | Source | Safe |
|---|---|---|---|---|---|
| `CLAUDE_MEM_CONTEXT_OBSERVATIONS` | `50` | int (1-?) | Total observations injected; also drives `/learn-codebase` CLAUDE.md gen and folder-md gen | cg L693, ws L10216 / L10269 / L11175 | yes — raise to 100-200 for richer recall |
| `CLAUDE_MEM_CONTEXT_FULL_COUNT` | `0` | int 0-20 | How many of those obs get rendered as **full narrative/facts** (rest are titles only). Validated `0<=x<=20` | ws L11408 | yes — try 5-10 |
| `CLAUDE_MEM_CONTEXT_FULL_FIELD` | `narrative` | enum `narrative\|facts` | Which field of the full-rendered obs to show | ws L11408 | yes |
| `CLAUDE_MEM_CONTEXT_SESSION_COUNT` | `10` | int 1-50 | How many recent sessions surface in injection | ws L10216 | yes |
| `CLAUDE_MEM_CONTEXT_OBSERVATION_TYPES` | (unset) | csv | Filter — only obs whose `type` is in this list | ws L11408 listed in valid keys | yes — narrow to types you care about |
| `CLAUDE_MEM_CONTEXT_OBSERVATION_CONCEPTS` | (unset) | csv | Filter — only obs tagged with these concepts | ws L11408 | yes |
| `CLAUDE_MEM_SEMANTIC_INJECT` | `false` | bool | Calls `/api/context/semantic` with the user's first prompt (>=20 chars) and prepends top-k chroma matches | ws L10121 | yes — turn on if Chroma is healthy |
| `CLAUDE_MEM_SEMANTIC_INJECT_LIMIT` | `5` | int | k for semantic injection | ws L10121 | yes |
| `CLAUDE_MEM_EXCLUDED_PROJECTS` | (empty) | csv | Project-name patterns skipped from capture **and** injection | ws L10107 / L11163 | yes |

### Group: Display — banner / status-line cosmetics
| `CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY` | `true` | bool | Render last-session summary at top of block | ws L10216 | yes |
| `CLAUDE_MEM_CONTEXT_SHOW_LAST_MESSAGE` | `false` | bool | Render last user message verbatim | ws L10216 | yes |
| `CLAUDE_MEM_CONTEXT_SHOW_READ_TOKENS` | `false` | bool | Show "context tokens read" stat | ws L10216 | yes |
| `CLAUDE_MEM_CONTEXT_SHOW_WORK_TOKENS` | `false` | bool | Show "work tokens" stat | ws L10216 | yes |
| `CLAUDE_MEM_CONTEXT_SHOW_SAVINGS_AMOUNT` | `false` | bool | Show absolute tokens saved | ws L10216 | yes |
| `CLAUDE_MEM_CONTEXT_SHOW_SAVINGS_PERCENT` | `true` | bool | Show % saved | ws L10216 | yes |
| `CLAUDE_MEM_CONTEXT_SHOW_TERMINAL_OUTPUT` | `true` | bool | Whether hook prints colored banner to stdout (vs. silent inject only) | ws L10225 | yes — set `false` for a quieter terminal |
| `CLAUDE_MEM_WELCOME_HINT_ENABLED` | `true` | bool | New-project welcome hint on first session | ws L11406 | yes |

### Group: Capture — what becomes an observation
| `CLAUDE_MEM_SKIP_TOOLS` | `ListMcpResourcesTool,SlashCommand,Skill,TodoWrite,AskUserQuestion` | csv | Tools whose calls are NOT captured | ws L11163 | yes — adding `Read,Grep` would slash noise |
| `CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED` | `false` | bool | When set, post-session generates per-folder CLAUDE.md files in dirs you touched | ws L11175 | yes |
| `CLAUDE_MEM_FOLDER_USE_LOCAL_MD` | `false` | bool | Use `local.md` filename instead of `CLAUDE.md` (avoids polluting project memory) | ws L11165 | yes |
| `CLAUDE_MEM_FOLDER_MD_EXCLUDE` | `[]` | JSON array | Path patterns excluded from folder-md generation | ws L11175 | yes |

### Group: Compression — model & tier routing
| `CLAUDE_MEM_MODEL` | `claude-haiku-4-5-20251001` | string | Default Claude model for summarization | ws L11268 / L11416 | yes |
| `CLAUDE_MEM_TIER_ROUTING_ENABLED` | `true` | bool | Route easy sessions to a cheaper model | ws L11370 | yes |
| `CLAUDE_MEM_TIER_SIMPLE_MODEL` | `haiku` | string | Model alias for "simple" tier | ws L11370 | yes |
| `CLAUDE_MEM_TIER_SUMMARY_MODEL` | (empty) | string | Optional override for summary-tier sessions | ws L11370 | yes |
| `CLAUDE_MEM_MAX_CONCURRENT_AGENTS` | `2` | int | Max parallel SDK-query agents the worker fans out | ws L11267 | cautious — RAM & API rate |

### Group: Provider — claude / gemini / openrouter
| `CLAUDE_MEM_PROVIDER` | `claude` | enum `claude\|gemini\|openrouter` | Which LLM provider does compression | ws L11268 | yes if you have keys |
| `CLAUDE_MEM_CLAUDE_AUTH_METHOD` | `subscription` | enum `subscription\|api-key\|gateway\|cli` | How to auth to Claude | ws L11408 | yes |
| `CLAUDE_MEM_GEMINI_API_KEY` | (empty) | secret | Gemini key (also reads `GEMINI_API_KEY` env) | ws L11268 | n/a |
| `CLAUDE_MEM_GEMINI_MODEL` | `gemini-2.5-flash-lite` | enum (lite/flash/3-flash-preview) | Gemini model | ws L11268 / L11408 | n/a |
| `CLAUDE_MEM_GEMINI_RATE_LIMITING_ENABLED` | `true` | bool | Throttle Gemini calls | ws L11268 | n/a |
| `CLAUDE_MEM_GEMINI_MAX_CONTEXT_MESSAGES` | `20` | int 1-100 | Window trimming | ws L11268 | n/a |
| `CLAUDE_MEM_GEMINI_MAX_TOKENS` | `100000` | int 1000-1000000 | Per-call cap | ws L11268 | n/a |
| `CLAUDE_MEM_OPENROUTER_API_KEY` | (empty) | secret | OpenRouter key (also `OPENROUTER_API_KEY`) | ws L11268 | n/a |
| `CLAUDE_MEM_OPENROUTER_MODEL` | `xiaomi/mimo-v2-flash:free` | string | OpenRouter model id | ws L11268 | n/a |
| `CLAUDE_MEM_OPENROUTER_SITE_URL` | (empty) | URL | OpenRouter HTTP-Referer | ws L11268 | n/a |
| `CLAUDE_MEM_OPENROUTER_APP_NAME` | `claude-mem` | string | OpenRouter X-Title | ws L11268 | n/a |
| `CLAUDE_MEM_OPENROUTER_MAX_CONTEXT_MESSAGES` | `20` | int 1-100 | Window trimming | ws L11268 | n/a |
| `CLAUDE_MEM_OPENROUTER_MAX_TOKENS` | `100000` | int 1k-1M | Per-call cap | ws L11268 | n/a |

### Group: Vector DB (Chroma)
| `CLAUDE_MEM_CHROMA_ENABLED` | `true` | bool | If false → SQLite-only search (no embeddings) | ws L10972 | yes — leaving on |
| `CLAUDE_MEM_CHROMA_MODE` | `local` | enum `local\|remote` | Spawn local chroma vs. hit remote | ws L10272 | yes |
| `CLAUDE_MEM_CHROMA_HOST` | `127.0.0.1` | host | Only used in `remote` mode | ws L10272 | yes |
| `CLAUDE_MEM_CHROMA_PORT` | `8000` | int | ditto | ws L10272 | yes |
| `CLAUDE_MEM_CHROMA_SSL` | `false` | bool | Remote TLS | ws L10272 | yes |
| `CLAUDE_MEM_CHROMA_API_KEY` | (empty) | secret | Remote auth | ws L10272 | yes |
| `CLAUDE_MEM_CHROMA_TENANT` | `default_tenant` | string | Remote tenant | ws L10272 | yes |
| `CLAUDE_MEM_CHROMA_DATABASE` | `default_database` | string | Remote DB | ws L10272 | yes |

### Group: Notifications (Telegram)
| `CLAUDE_MEM_TELEGRAM_ENABLED` | `true` | bool | Master switch — but no-op without token+chat | ws L11165 | yes |
| `CLAUDE_MEM_TELEGRAM_BOT_TOKEN` | (empty) | secret | Telegram bot | ws L11165 | n/a |
| `CLAUDE_MEM_TELEGRAM_CHAT_ID` | (empty) | string | Destination chat | ws L11165 | n/a |
| `CLAUDE_MEM_TELEGRAM_TRIGGER_TYPES` | `security_alert` | csv | Obs types that trigger push | ws L11165 | n/a |
| `CLAUDE_MEM_TELEGRAM_TRIGGER_CONCEPTS` | (empty) | csv | Obs concepts that trigger push | ws L11165 | n/a |

### Group: Queue (job backplane)
| `CLAUDE_MEM_QUEUE_ENGINE` | `sqlite` | enum `sqlite\|bullmq` | Backing job queue | ws L11013 | NO — bullmq needs Redis we don't run |
| `CLAUDE_MEM_REDIS_URL` | (empty) | URL `redis://` or `rediss://` | Used by bullmq engine | ws L11013 | n/a |
| `CLAUDE_MEM_REDIS_HOST` | `127.0.0.1` | host | ditto | ws L11013 | n/a |
| `CLAUDE_MEM_REDIS_PORT` | `6379` | int 1-65535 | ditto | ws L11013 | n/a |
| `CLAUDE_MEM_REDIS_MODE` | `external` | enum `external\|managed\|docker` | How redis is brought up | ws L11013 | n/a |
| `CLAUDE_MEM_QUEUE_REDIS_PREFIX` | `claude_mem_37777` | string | Key namespace | ws L11013 | n/a |

### Group: Watcher (transcripts)
| `CLAUDE_MEM_TRANSCRIPTS_ENABLED` | `true` | bool | If false → no automatic transcript ingest | ws L11420 | yes |
| `CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH` | `~/.claude-mem/transcript-watch.json` | path | Where the watch-list lives | ws L11420 | yes |

### Group: Worker (daemon config)
| `CLAUDE_MEM_WORKER_PORT` | `37777` | int 1024-65535 | HTTP API port (`/api/*`); also seeds queue-prefix and server-beta URL | ws L20, L10314 | NO — moving it strands plugin clients |
| `CLAUDE_MEM_WORKER_HOST` | `127.0.0.1` | IP | Bind addr (validated against IPv4 regex/`localhost`) | ws L11408 | only to `0.0.0.0` if you actually want remote access |
| `CLAUDE_MEM_RUNTIME` | `worker` | enum `worker\|server-beta` | Which backend the hook talks to (local daemon vs. cloud) | ws L10121 | NO unless you've set up server-beta |
| `CLAUDE_MEM_HOOK_FAIL_LOUD_THRESHOLD` | `3` | int >=1 | Consecutive hook failures before user-visible warning | cg L693 (`b8e`) | yes |

### Group: Folder context (per-folder CLAUDE.md)
Already listed under Capture (`CLAUDE_MEM_FOLDER_*`).

### Group: Cloud sync (server-beta)
| `CLAUDE_MEM_SERVER_BETA_URL` | `http://127.0.0.1:37954` | URL | Cloud endpoint (also fallback for failed local writes) | ws L10121 | n/a — feature not configured |
| `CLAUDE_MEM_SERVER_BETA_API_KEY` | (empty) | secret | Auth | ws L10121 | n/a |
| `CLAUDE_MEM_SERVER_BETA_PROJECT_ID` | (empty) | string | Project scope | ws L10121 | n/a |

### Group: Auth
| `CLAUDE_MEM_AUTH_MODE` | `api-key` | string | Worker's own HTTP API auth mode for `/v1/*` admin endpoints (header `authorization`) | ws L10694 | leave |
| (undeclared) `CLAUDE_MEM_ALLOW_LOCAL_DEV_BYPASS` | `0` | bool ("1"=on) | Bypass auth for localhost. Not in DEFAULTS — only consulted at L10694 | code-only | NO in production |

### Group: Runtime
| `CLAUDE_MEM_MODE` | `code` | string | Profile selector for prompts ("code" vs. presumed alternatives). Not validated; pure passthrough | ws L20 (DEFAULTS only — appears unused elsewhere in this bundle) | leave |

### Group: Operational
| `CLAUDE_MEM_DATA_DIR` | `C:\Users\radmo\.claude-mem` | path | Root for DB, logs, transcript-watch, claudemd cache | cg L9 `Ft()`, ws L12 `$re()` | NO — moving breaks data |
| `CLAUDE_MEM_LOG_LEVEL` | `INFO` | enum DEBUG/INFO/WARN/ERROR/SILENT | Logger threshold | cg L1, ws L12 | yes |
| `CLAUDE_MEM_PYTHON_VERSION` | `3.13` | `3.X` or `3.XX` | Used by `uvx` to spawn Chroma | ws L10272 / L11408 | yes (must match an installed Python) |
| `CLAUDE_CODE_PATH` | (empty) | abs path | Override Claude CLI binary path; existence validated at startup | ws L11160 | only if you need a non-default CLI |

---

## Sleeper knobs worth flagging (in our profile)

1. **`CLAUDE_MEM_CONTEXT_FULL_COUNT=5`** — currently `0`, so injected obs are titles only. Setting `5-10` with `FULL_FIELD=narrative` would give us actual prose recall instead of headlines — huge quality lift, modest token cost. Validated 0-20.
2. **`CLAUDE_MEM_SEMANTIC_INJECT=true` + `LIMIT=5-10`** — Chroma is already on (`CHROMA_ENABLED=true`). Flipping this calls `/api/context/semantic` against the user's first prompt and prepends top-k obs. For "did we solve X before?" this beats the static last-N injection.
3. **`CLAUDE_MEM_SKIP_TOOLS`** — currently 5 tools. Adding `Read,Grep,Glob,Bash` would cut routine read-only noise. (Risk: lose audit trail of files we touched. Decide per-project.)
4. **`CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED=true` + `FOLDER_USE_LOCAL_MD=true`** — auto-generates per-folder `local.md` summaries after sessions. The `local.md` form keeps them out of git/project memory. Compounding cognitive cache without bloating root CLAUDE.md.
5. **`CLAUDE_MEM_TIER_ROUTING_ENABLED=true` (already)** — keep. With `TIER_SIMPLE_MODEL=haiku` it auto-downshifts cheap sessions. Confirm by setting `LOG_LEVEL=DEBUG` and watching `Tier routing: simple model` log lines.

## Dead-end knobs (skip)

- **All `CLAUDE_MEM_GEMINI_*`** — we're on `claude` provider, no Gemini key. Validators won't trip but values are inert.
- **All `CLAUDE_MEM_OPENROUTER_*`** — same.
- **All `CLAUDE_MEM_TELEGRAM_*`** — no bot configured.
- **All `CLAUDE_MEM_REDIS_*` and `QUEUE_ENGINE=bullmq`** — we don't run Redis. `sqlite` engine is correct.
- **All `CLAUDE_MEM_SERVER_BETA_*` + `RUNTIME=server-beta`** — cloud-sync feature not provisioned (`http://127.0.0.1:37954` placeholder).
- **`CLAUDE_MEM_CHROMA_MODE=remote` + remote chroma vars** — local chroma works.
- **`CLAUDE_MEM_AUTH_MODE` / `ALLOW_LOCAL_DEV_BYPASS`** — daemon is loopback-only.
- **`CLAUDE_CODE_PATH`** — leave empty; default resolution works.

---

## How overrides flow
1. `Pe.loadFromFile(Jt)` reads `~/.claude-mem/settings.json` (`Jt` = path to `settings.json` under `CLAUDE_MEM_DATA_DIR`). File `env` block wins.
2. Anything missing falls back to `process.env[k]`.
3. Anything still missing falls back to `DEFAULTS[k]`.
4. `/api/settings` returns the merged result (what `curl` showed).

To change a value: edit `~/.claude-mem/settings.json` (key is just the var name at the top-level `env` block), then `pkill claude-mem` or restart the worker.

## Source line index (canonical lookups)
- DEFAULTS block: `worker-service.cjs:20` (full), `context-generator.cjs:693` (mirror)
- Context injection assembly: `worker-service.cjs:10216`
- Semantic inject hook: `worker-service.cjs:10121`
- Skip-tools / project-excluded filter: `worker-service.cjs:11163`
- Folder-md generator: `worker-service.cjs:11175`
- Tier routing: `worker-service.cjs:11370`
- Telegram dispatcher: `worker-service.cjs:11165`
- Queue/Redis config: `worker-service.cjs:11013`
- Chroma uvx spawn: `worker-service.cjs:10272`
- Auth middleware: `worker-service.cjs:10694`
- Settings validator (all bounded-int / enum checks): `worker-service.cjs:11408`
