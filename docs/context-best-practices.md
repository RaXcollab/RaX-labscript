# Context Engineering Best Practices

Last updated: 2026-05-19

Corroborated findings from online sources. Each practice tagged with source count and tier.
Anthropic official [A] > Expert practitioners [E] > Community [C].

## CLAUDE.md (5+ sources)

- **Target <200 lines per file** — longer files reduce adherence; rules get lost in noise
  [A: code.claude.com/best-practices, A: code.claude.com/memory, E: SFEIR, E: Shankar, C: shanraisshan]

- **Only include what Claude gets wrong without it** — if Claude already does it correctly, delete the rule
  [A: code.claude.com/best-practices, E: Shankar, E: Clune]

- **Prefer pointers over copies** — use `@path/to/file` refs and path-scoped rules instead of inlining content
  [A: code.claude.com/best-practices, A: code.claude.com/memory, E: Bojie Li]

- **Use progressive disclosure** — CLAUDE.md is the index; details live in docs/, rules/, skills/
  [A: code.claude.com/memory, E: Bojie Li, E: SFEIR]

- **Treat CLAUDE.md like code** — review when things go wrong, prune regularly, test by observing behavior changes
  [A: code.claude.com/best-practices, E: Shankar]

## Context Window Management (6+ sources)

- **Context is the #1 resource to manage** — LLM performance degrades as context fills; intelligence is not the bottleneck
  [A: code.claude.com/best-practices, E: Bojie Li, E: SFEIR, E: Clune]

- **/clear between unrelated tasks** — mixed domains degrade performance; a clean session with a better prompt beats a long session with corrections
  [A: code.claude.com/best-practices, E: Shankar, E: SFEIR, E: Clune]

- **After 2 failed corrections, /clear and rewrite the prompt** — context is polluted with failed approaches
  [A: code.claude.com/best-practices, E: Shankar]

- **Monitor fill level; suggest document & clear past ~50%** — response relevance drops from 94% to 72% at saturation
  [E: SFEIR (specific metrics), E: Shankar, E: Clune]

- **Use subagents for investigation** — they explore in a separate context window and return summaries, keeping main context clean
  [A: code.claude.com/best-practices, A: code.claude.com/sub-agents, E: SFEIR, E: Shankar]

- **Multi-session splits outperform single saturated sessions** — 3x40k tokens beats 1x180k tokens (2.1s vs 8.2s response, 94% vs 72% relevance)
  [E: SFEIR (specific metrics), E: Shankar]

## Agent & Subagent Patterns (4+ sources)

- **Scope tools per agent** — read-only agents get Read/Grep/Glob; writers get Edit/Write/Bash; omitting tools grants all
  [A: code.claude.com/sub-agents, E: Shankar, C: PubNub, C: claudefast]

- **Reserve custom subagents for true domain expertise** — generic context-gating subagents create rigid workflows; let main agent delegate dynamically
  [E: Shankar, A: code.claude.com/best-practices]

- **Provide comprehensive context in spawn prompts** — subagents don't inherit conversation history; include file paths, requirements, and success criteria
  [A: code.claude.com/sub-agents, C: PubNub, C: claudekit]

- **Plan mode blocks web tools for subagents** — do web research from main thread during planning
  [Observed directly, 2026-03-06]

## Verification & Workflow (4+ sources)

- **Give Claude a way to verify its own work** — tests, screenshots, linters, expected outputs. Single highest-leverage practice
  [A: code.claude.com/best-practices (explicit "highest leverage"), E: Clune, E: Shankar]

- **Explore -> Plan -> Implement -> Commit** — separate research from execution to avoid solving the wrong problem
  [A: code.claude.com/best-practices, E: Shankar, E: Clune]

- **Skip planning for small tasks** — if you can describe the diff in one sentence, just do it
  [A: code.claude.com/best-practices]

- **Use hooks for deterministic requirements, CLAUDE.md for advisory** — hooks guarantee execution; CLAUDE.md is best-effort
  [A: code.claude.com/best-practices, A: code.claude.com/memory]

## Memory & Persistence (3+ sources)

- **CLAUDE.md survives /compact; conversation-only instructions do not** — write important things to files
  [A: code.claude.com/memory, E: Shankar, E: Clune]

- **Auto memory MEMORY.md: first 200 lines loaded; rest on demand** — keep the index concise, use topic files for details
  [A: code.claude.com/memory]

- **Use git commits as context boundaries** — completed work persists across sessions via version control
  [E: Clune, E: Shankar]

- **"Document & Clear" pattern** — for complex tasks, write progress to markdown, /clear, resume by reading that file
  [E: Shankar, E: Clune]

## Maintenance (meta-practice)

- **Periodically re-research and update this document** — Claude Code evolves rapidly; best practices from 6 months ago may be outdated. Run a web research session quarterly to check for new official guidance. Update the "Last updated" date when modifying
  [A: code.claude.com/best-practices ("prune regularly"), E: Shankar ("meta-analysis on session logs")]

## Token Budget Reference (2+ sources)

- System prompt + CLAUDE.md: 3k-8k tokens (2-4% of 200k window)
- Auto-read files: 10k-50k tokens (5-25%)
- Conversation history: 30k-120k tokens (15-60%)
- Total CLAUDE.md + rules + memory target: <10k tokens
  [E: SFEIR, A: code.claude.com/memory (200-line limit implies ~4k tokens)]

## Sources

- [Anthropic: Best Practices](https://code.claude.com/docs/en/best-practices)
- [Anthropic: Memory](https://code.claude.com/docs/en/memory)
- [Anthropic: Subagents](https://code.claude.com/docs/en/sub-agents)
- [Shrivu Shankar](https://blog.sshh.io/p/how-i-use-every-claude-code-feature)
- [SFEIR Institute](https://institute.sfeir.com/en/claude-code/claude-code-context-management/optimization/)
- [Arthur Clune](https://clune.org/posts/anthropic-context-engineering/)
- [Bojie Li](https://01.me/en/2025/12/context-engineering-from-claude/)
