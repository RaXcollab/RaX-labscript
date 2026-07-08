---
name: github-auth-triage
description: Deterministic triage for GitHub connectivity/auth failures (gh CLI, GitHub MCP, 401s, device flow). Use whenever GitHub access fails or an MCP shows "failed to connect" — BEFORE deleting credentials or re-authenticating.
---

# GitHub Auth Triage

Run in order; stop at the first decisive answer. Never start with credential surgery.

1. **Establish state first:** `gh auth status` AND the /mcp list. Installed, enabled, and authed are three different things — do not conflate them.
2. **GitHub MCP requires a Copilot seat.** No seat → auth will NEVER succeed; stop and tell the user. Check this before any OAuth/PAT surgery.
3. **Never "delete credential + re-auth" as a first move** — it is the last resort (signature that justifies it: token fields present but zero-length, no refreshToken). RaXcollab repos are public: unauthenticated REST reads (`gh api /repos/RaXcollab/<repo>` or curl) separate "auth broken" from "network broken" for free.
4. **Device flow:** confirm the target GitHub account with the user BEFORE requesting a code.
5. **On 401 / HTTP 400:** capture the exact error body, report it, stop. Do not restart-loop the auth flow.
