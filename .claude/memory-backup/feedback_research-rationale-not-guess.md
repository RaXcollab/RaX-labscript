---
name: Research before writing rationale comments — don't ship guesses as facts
description: When annotating code with a "why" comment, either verify against vendor docs first, or omit the speculative rationale. Don't write plausible-sounding hypotheses in code as if they were facts.
type: feedback
originSessionId: 9db9ac08-3097-4f43-8ecb-8652d9dbc29a
---
When adding a rationale comment to code (the "why" behind a non-obvious choice), either research the claim first or omit it. Don't ship a plausible-sounding hypothesis as if it were a researched fact.

**Why:** During 2026-05-05 wavemeter session, I demoted `HIGH_PRIORITY_CLASS → ABOVE_NORMAL` and added a comment claiming HIGH "can confuse the Win11 Thread Director on hybrid CPUs" — which sounded reasonable but was a guess. The user pushed back ("did you actually look into my question?"), I had to research it, and the real reason was completely different (Microsoft's explicit "HIGH is for brief events, not sustained loops" guidance). The original comment would have misled a future reader for years.

**How to apply:**
- Before writing a "why" / rationale comment, ask: have I verified this against vendor docs, code, or measurement? If no → either research it now, or write only what I know to be true and omit the speculation.
- Speculative rationale is worse than no rationale — it's load-bearing misinformation that lives in the code.
- If the rationale really does combine fact + hypothesis, separate them explicitly: "Per [vendor doc]: X. Plausibly also helps with Y, but unverified."
- This rule applies most strongly to comments that justify *changes* (e.g., "demoted X because Z") — those will be the first thing a future reader looks at when re-evaluating the decision.
