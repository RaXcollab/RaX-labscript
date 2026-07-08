# PostToolUse (Edit|Write, if-filtered in settings.json): stamp the device-edit
# marker. The path regex here is defense-in-depth for the settings-level `if`
# rules; both must list the same four trees. Separator-anchored on both sides so
# e.g. docs/user_devices_overview.md cannot false-positive (audit finding A3).
. "$PSScriptRoot\_hook-common.ps1"

$in = Read-HookInput
if (-not $in) { exit 0 }   # marker hooks fail open: no marker beats a wrong one
$sid = $in.session_id
if ([string]::IsNullOrEmpty($sid)) { exit 0 }

$p = $in.tool_input.file_path
if (-not $p) { exit 0 }

if ($p -match '[\\/](user_devices|blacs|labscript-devices|labscript-utils)[\\/]') {
    Set-Marker 'device-edit' $sid
}
exit 0
