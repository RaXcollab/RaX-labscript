# SubagentStart (research-type agents): inject the source-discipline contract.
# Output-only hook — no stdin read needed.
$ctx = "SOURCE DISCIPLINE (lab contract): every factual claim (config key, env var, default value, commit-is-safe verdict) must carry a primary-source citation you actually fetched this run, or be tagged 'UNVERIFIED - needs confirmation'. Never invent doc URLs. WebFetch is hook-blocked on this machine - use ctx_fetch_and_index or WebSearch."
@{ hookSpecificOutput = @{ hookEventName = 'SubagentStart'; additionalContext = $ctx } } |
    ConvertTo-Json -Depth 4 -Compress | Write-Output
exit 0
