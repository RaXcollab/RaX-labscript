# SubagentStop (matcher: blacs-expert): stamp the audit marker. Known accepted
# limitation: any blacs-expert run counts, regardless of what it audited — the
# mtime ordering in check-audit-gate.ps1 (audit must be NEWER than last edit)
# closes the worst case (early unrelated audit, later unaudited edit).
. "$PSScriptRoot\_hook-common.ps1"

$in = Read-HookInput
if ($in) { Set-Marker 'audit-ran' $in.session_id }
exit 0
