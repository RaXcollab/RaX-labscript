# Block recursive removal and broad directory moves until the user approves them.
. "$PSScriptRoot\_hook-common.ps1"

$inputData = Read-HookInput
if (-not $inputData) { exit 0 }

$command = $inputData.tool_input.command
if (-not $command) { exit 0 }

function Deny([string]$message) {
    [Console]::Error.WriteLine($message)
    exit 2
}

$recursiveRemove = '(?i)(^|[;&|]\s*)rm\s+(--recursive\b|-[a-z]*r[a-z]*\b)'
$powerShellRemove = '(?i)Remove-Item\b[^;|\r\n]*\s-Recurse\b'

if ($command -match $recursiveRemove -or $command -match $powerShellRemove) {
    Deny 'DELETION GUARD: recursive removal requires explicit user approval.'
}

$directoryMove = '(?i)(^|[;&|]\s*)mv\s+(-[^\s]+\s+)*["'']?[^\s"'']+[\\/]["'']?\s+'
if ($command -match $directoryMove) {
    Deny 'MOVE GUARD: a directory move requires explicit user approval.'
}

exit 0
