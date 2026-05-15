---
paths:
  - ".claude/**"
  - "CLAUDE.md"
  - "docs/*.md"
---

# Instruction File Writing Rules

## Style
- **Direct imperatives** — "Do X", "Never Y". Not "you should" or "consider"
- **One concept per bullet** — no narrative paragraphs. Sub-explanations use indented sub-bullets
- **Challenge each line** — would removing it cause mistakes? If not, cut it
- **Specific and actionable** — exact commands, file paths, class names. Not "be careful" or "handle properly"
- **No hedging** — no "might want to", "consider", "it's recommended"
- **Front-load critical info** — most dangerous/important rules first in each section
- **Bold key terms** for scannability
- **Consistent terminology** — pick one term, use it everywhere
- **No conflicting instructions** — before adding a rule, check if it contradicts an existing one. If two rules could be read as opposing, resolve them explicitly with precedence

## Structure (CLAUDE.md)
- **Target < 140 lines** — LLMs follow ~150-200 instructions; system prompt already uses ~50
- **WHY / WHAT / HOW** — explain purpose, describe architecture, give actionable commands
- **Progressive disclosure** — CLAUDE.md has pointers (`@docs/file.md`); details live in referenced docs
- **No code style rules** — use linters instead. LLMs learn patterns from existing code in-context
- **Token budget** — always-loaded context (CLAUDE.md + unconditional rules + auto-memory + agent descriptions) should stay under 8k tokens. Run context-auditor to measure
- **Review after each multi-session project** — prune stale rules, resolve contradictions, update patterns

## Structure (docs/ and .claude/rules/)
- **docs/*.md** — domain reference (patterns, API, conventions). Loaded via `@docs/` in CLAUDE.md
- **.claude/rules/*.md** — path-scoped rules. Auto-loaded when editing matching files. Keep narrow and imperative
- **memory/*.md** — cross-session lessons, device internals. Loaded into auto-memory context

@docs/context-best-practices.md
