$null = [Console]::In.ReadToEnd()
$ctx = "Session-start checklist: (1) launch the session-notes agent in the background now; (2) Read .claude/open-items.md and surface anything blocking today's work."
@{ hookSpecificOutput = @{ hookEventName = "SessionStart"; additionalContext = $ctx } } |
  ConvertTo-Json -Depth 4 -Compress | Write-Output
exit 0
