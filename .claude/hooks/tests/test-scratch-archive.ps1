# Self-check for Invoke-ScratchArchive (_hook-common.ps1).
# Run: pwsh -File .claude/hooks/tests/test-scratch-archive.ps1  → prints PASS or throws.
. "$PSScriptRoot\..\_hook-common.ps1"

$dir = Join-Path $env:TEMP "scratch-archive-test-$PID"
New-Item -ItemType Directory -Force $dir | Out-Null
$scratch = Join-Path $dir 'session-scratch.md'
$archive = Join-Path $dir 'session-scratch-archive.md'
$oldDate = (Get-Date).AddDays(-30).ToString('yyyy-MM-dd')
$newDate = (Get-Date).ToString('yyyy-MM-dd')
@"
## Session: $oldDate — old work
- old entry
## $newDate ~10:00 — fresh work
- fresh entry
## undated pause section
- kept because header has no date
"@ | Set-Content $scratch

Invoke-ScratchArchive $scratch

$live = Get-Content $scratch -Raw
$arch = Get-Content $archive -Raw
if ($live -match 'old entry')             { throw 'old section not removed from live file' }
if ($live -notmatch 'fresh entry')        { throw 'fresh section wrongly removed' }
if ($live -notmatch 'undated pause')      { throw 'undated section wrongly removed' }
if ($arch -notmatch 'old entry')          { throw 'old section missing from archive' }

# all sections old → live file deleted, content preserved in archive
"## Session: $oldDate — only old`n- lone entry" | Set-Content $scratch
Invoke-ScratchArchive $scratch
if (Test-Path $scratch) { throw 'all-old live file not deleted' }
if ((Get-Content $archive -Raw) -notmatch 'lone entry') { throw 'deleted content missing from archive' }

# missing file → no-op, no error
Invoke-ScratchArchive (Join-Path $dir 'does-not-exist.md')

Remove-Item -Recurse -Force $dir
'PASS'
