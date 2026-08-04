# PostToolUse (Edit|Write, every file): stamp the device-edit marker. This
# regex is the ONLY path filter — the 8 settings-level `if` rules were
# collapsed into one unconditional entry 2026-08-03 (ponytail: script already
# self-filtered, two lists to keep in sync). Separator-anchored on both sides so
# e.g. docs/user_devices_overview.md cannot false-positive (audit finding A3).
# NOTE: the leading separator means this only matches ABSOLUTE paths, which is
# what Edit/Write always send; a repo-relative 'labscript-devices/...' would not
# match (only 'blacs/blacs/...' does, by accident of the duplicated dirname).
# Pure-docs extensions are excluded: a CLAUDE.md write under one of the trees
# carries no device-code risk but armed the gate anyway (2026-07-29). DENYlist,
# not allowlist -- an unrecognized extension still gates, because a missed audit
# costs more than a spurious one. .txt/.ini/.json deliberately still gate: BLACS
# hashes those as connection-table inputs
# (blacs/blacs/plugins/connection_table/__init__.py:207).
. "$PSScriptRoot\_hook-common.ps1"

$in = Read-HookInput
if (-not $in) { exit 0 }   # marker hooks fail open: no marker beats a wrong one
$sid = $in.session_id
if ([string]::IsNullOrEmpty($sid)) { exit 0 }

$p = $in.tool_input.file_path
if (-not $p) { exit 0 }

if ($p -match '[\\/](user_devices|blacs|labscript-devices|labscript-utils)[\\/]' -and
    $p -notmatch '\.(md|rst|html?)$') {
    Set-Marker 'device-edit' $sid
}
exit 0
