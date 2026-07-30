# PostToolUse (Edit|Write): syntax-check the edited/written .py file so
# device-class typos surface at edit time instead of on BLACS restart.
# PostToolUse cannot block (tool already ran) -- report via additionalContext,
# never exit 2 (that's a non-blocking error notice, not feedback) and never
# the decision-block key (reserved for hard failures, not mere syntax errors).
# __pycache__ writes from py_compile are fine (CLAUDE.md Do NOT Flag These).
. "$PSScriptRoot\_hook-common.ps1"

$in = Read-HookInput
if (-not $in) { exit 0 }

$p = $in.tool_input.file_path
if (-not $p) { exit 0 }
if ($p -notmatch '\.py$') { exit 0 }
if (-not (Test-Path -LiteralPath $p)) { exit 0 }

$pythonExe = 'C:\Users\radmo\miniconda\envs\labscript\python.exe'
# _hook-common.ps1 sets ErrorActionPreference=Stop; on PS 7.3+ that turns a
# native command's stderr output into a terminating error. Scope it off here
# so a py_compile syntax error is just captured output, not a thrown exception.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$result = & $pythonExe -m py_compile "$p" 2>&1
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
if ($exitCode -eq 0) { exit 0 }

$msg = "SYNTAX ERROR in $p`: $($result -join "`n"). Fix before proceeding."
$output = @{
    hookSpecificOutput = @{
        hookEventName    = 'PostToolUse'
        additionalContext = $msg
    }
} | ConvertTo-Json -Compress
Write-Output $output
exit 0
