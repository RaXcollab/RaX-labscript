# SessionStart (startup|resume|clear): reset this session's markers, anchor the
# session-start time, inject the checklist. Marker cleanup on RESUME is the fix
# for multi-day sessions inheriting a stale "audited" state (audit finding C4).
. "$PSScriptRoot\_hook-common.ps1"

$in = Read-HookInput
if ($in) {
    Remove-SessionMarkers $in.session_id
    Set-Marker 'session-start' $in.session_id   # mtime anchor for the deferral gate
}

$ctx = "Session-start checklist: (1) launch the session-notes agent in the background now; (2) Read .claude/open-items.md and surface anything blocking today's work."
@{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $ctx } } |
    ConvertTo-Json -Depth 4 -Compress | Write-Output
exit 0
