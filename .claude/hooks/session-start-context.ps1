# SessionStart (startup|resume|clear): reset this session's markers, anchor the
# session-start time, inject the checklist. Marker cleanup on RESUME is the fix
# for multi-day sessions inheriting a stale "audited" state (audit finding C4).
. "$PSScriptRoot\_hook-common.ps1"

$in = Read-HookInput
if ($in) {
    Remove-SessionMarkers $in.session_id
    Set-Marker 'session-start' $in.session_id   # mtime anchor for the deferral gate
}

# Sections older than 7 days rotate out mechanically — wrap-up trimming alone
# let the file grow unbounded (52 KB / 18 sections by 2026-08-20).
Invoke-ScratchArchive (Join-Path (Split-Path $PSScriptRoot -Parent) 'session-scratch.md')

$ctx = "Session-start checklist: (1) log milestones by appending TERSE timestamped entries (bullet, file paths, one-line rationale) to .claude/session-scratch.md — no session-notes agent, no per-milestone subagents; (2) if .claude/session-scratch.md exists from a prior session, surface it and offer to run wrap-up before new work (sections older than 7 days are auto-archived to .claude/session-scratch-archive.md); (3) Read .claude/open-items.md and surface anything blocking today's work."
@{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $ctx } } |
    ConvertTo-Json -Depth 4 -Compress | Write-Output
exit 0
