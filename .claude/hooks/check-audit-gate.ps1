# Stop-time gates (warn-only: exit 2 on Stop feeds stderr back to Claude and the
# turn CONTINUES; the engine hard-caps at 8 consecutive blocks).
#   Gate 1 — device edits require a blacs-expert audit NEWER than the last edit
#            (mtime ordering fixes audit-then-edit passing silently), with an
#            explicit waiver marker so a sanctioned "not needed" doesn't nag.
#   Gate 2 — deferral language in the final message must land in
#            .claude/open-items.md (or be explicitly declined); warns once per
#            session. Uses last_assistant_message from the Stop input — the
#            docs-recommended path; no transcript parsing.
. "$PSScriptRoot\_hook-common.ps1"

$in = Read-HookInput
if (-not $in) { exit 0 }              # gates fail open by design (warn-only)
if ($in.stop_hook_active) { exit 0 }  # already inside a hook-triggered continuation
$sid = $in.session_id
if ([string]::IsNullOrEmpty($sid)) { exit 0 }

$warnings = @()

# --- Gate 1: unaudited device edits -----------------------------------------
$editT = Get-MarkerTime 'device-edit' $sid
if ($editT) {
    $auditT = Get-MarkerTime 'audit-ran' $sid
    $waiveT = Get-MarkerTime 'audit-waiver' $sid
    $covered = ($auditT -and $auditT -ge $editT) -or ($waiveT -and $waiveT -ge $editT)
    if (-not $covered) {
        $waiverPath = Get-MarkerPath 'audit-waiver' $sid
        $warnings += ("AUDIT GATE: files under user_devices/, blacs/, labscript-devices/ or labscript-utils/ were edited after the last blacs-expert audit. " +
            "Run the audit (Agent: blacs-expert, scope = blast radius, not diff size) and include verification evidence (helper tests / compile / BLACS restart result) in your report to the user. " +
            "If an audit is genuinely unnecessary, state the reason to the user AND waive this gate by running: New-Item -ItemType File -Force '$waiverPath'")
    }
}

# --- Gate 2: deferral language without a ledger entry (warn once/session) ----
$last = $in.last_assistant_message
if ($last -and $env:CLAUDE_PROJECT_DIR -and -not (Get-MarkerTime 'deferral-warned' $sid)) {
    $deferralPattern = '(?i)\b(follow[- ]up|pre-existing|future session|defer(red|ring)?|worth revisiting|revisit (this )?later)\b'
    if ($last -match $deferralPattern) {
        $hit = $Matches[0]
        $recorded = $false
        try {
            $openItems = Join-Path $env:CLAUDE_PROJECT_DIR '.claude\open-items.md'
            $startT = Get-MarkerTime 'session-start' $sid
            if ($startT -and (Test-Path -LiteralPath $openItems)) {
                $recorded = ((Get-Item -LiteralPath $openItems).LastWriteTimeUtc -ge $startT)
            }
        } catch {}
        if (-not $recorded) {
            Set-Marker 'deferral-warned' $sid
            $warnings += ("DEFERRAL GATE: your last message contains deferral language ('$hit') but .claude/open-items.md was not updated this session. " +
                "Prose footnotes do not survive compaction. Add the deferred item to .claude/open-items.md now, or state explicitly that it is already recorded / deliberately not tracked. (This warning fires once per session.)")
        }
    }
}

if ($warnings.Count -gt 0) {
    [Console]::Error.WriteLine(($warnings -join "`n`n"))
    exit 2
}
exit 0
