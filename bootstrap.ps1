<#
.SYNOPSIS
    Fetch the RaX labscript backend forks into place at the versions recorded in repos.yml.

.DESCRIPTION
    The labscript suite is this parent repo plus three backend forks (blacs,
    labscript-devices, labscript-utils). Nothing binds their versions together in
    git, so a fresh clone otherwise picks up whatever happens to be on each fork's
    default branch that day. This script closes that gap: it clones each backend
    into the correct folder and checks out the commit repos.yml pins.

    The external GUI applications under GUIs/ are deliberately out of scope. They
    are separate programs with their own repositories, conda environments, and
    install procedures.

    Safe to re-run. It never discards uncommitted work: a backend with a dirty
    working tree is reported and skipped.

.PARAMETER Latest
    Check out each backend's branch tip instead of its pinned commit.

.PARAMETER Install
    After syncing, run the editable install of the three backends. Requires the
    'labscript' conda environment to be active.

.PARAMETER UpdatePins
    Rewrite the pinned commits in repos.yml from each backend's current HEAD.
    Use after validating a new backend state; commit the result alongside the
    parent change that depends on it.

.EXAMPLE
    .\bootstrap.ps1
    Clone or update the backends to their pinned commits.

.EXAMPLE
    .\bootstrap.ps1 -Install
    Same, then run the editable install.

.EXAMPLE
    .\bootstrap.ps1 -UpdatePins
    Record the current backend HEADs as the new pins.
#>

[CmdletBinding()]
param(
    [switch]$Latest,
    [switch]$Install,
    [switch]$UpdatePins
)

# 'Continue', not 'Stop': git writes ordinary progress ("Switched to branch
# 'master'") to stderr, and Windows PowerShell 5.1 turns any native-command
# stderr into a NativeCommandError that 'Stop' escalates to a terminating error.
# Every git call below is checked explicitly via $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManifestPath = Join-Path $RepoRoot 'repos.yml'

function Write-Step  { param($m) Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok    { param($m) Write-Host "    $m" -ForegroundColor Green }
function Write-Warn2 { param($m) Write-Host "    $m" -ForegroundColor Yellow }
function Write-Err2  { param($m) Write-Host "    $m" -ForegroundColor Red }

function Read-Manifest {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Manifest not found: $Path"
    }

    $entries = @()
    $current = $null

    foreach ($line in (Get-Content $Path -Encoding utf8)) {
        if ($line -match '^\s*#') { continue }
        if ($line -match '^\s*-\s+name:\s*(\S+)') {
            if ($null -ne $current) { $entries += $current }
            $current = @{ name = $Matches[1] }
            continue
        }
        if ($null -eq $current) { continue }
        if ($line -match '^\s+(path|url|branch|pinned):\s*(\S+)') {
            $current[$Matches[1]] = $Matches[2]
        }
    }
    if ($null -ne $current) { $entries += $current }

    foreach ($e in $entries) {
        foreach ($key in @('path', 'url', 'branch', 'pinned')) {
            if (-not $e.ContainsKey($key)) {
                throw "Manifest entry '$($e.name)' is missing '$key'"
            }
        }
    }
    return $entries
}

function Test-CleanTree {
    param([string]$Dir)
    $status = & git -C $Dir status --porcelain
    return [string]::IsNullOrWhiteSpace(($status | Out-String))
}

# --- sanity: are we in the right place? -------------------------------------

if (-not (Test-Path (Join-Path $RepoRoot 'userlib'))) {
    Write-Err2 "No userlib/ next to this script - is this the labscript-suite parent repo?"
    exit 1
}

$expected = Join-Path $env:USERPROFILE 'labscript-suite'
if ($RepoRoot -ne $expected) {
    Write-Warn2 "This checkout is at:  $RepoRoot"
    Write-Warn2 "labscript expects it: $expected"
    Write-Warn2 "labscript_profile hardcodes ~/labscript-suite with no override."
    Write-Warn2 "Move it there, or junction it:"
    Write-Warn2 "  mklink /J `"$expected`" `"$RepoRoot`""
    Write-Warn2 "Continuing - the backends will still be fetched correctly."
    Write-Host ""
}

$backends = Read-Manifest -Path $ManifestPath

# --- update pins mode -------------------------------------------------------

if ($UpdatePins) {
    Write-Step "Recording current backend HEADs as pins"
    # -Encoding utf8 on both read and write: without it PS 5.1 decodes the file
    # as ANSI and mangles any non-ASCII character on the round-trip.
    $text = Get-Content $ManifestPath -Raw -Encoding utf8
    $changed = 0

    foreach ($b in $backends) {
        $dir = Join-Path $RepoRoot $b.path
        if (-not (Test-Path (Join-Path $dir '.git'))) {
            Write-Warn2 "$($b.name): not cloned, skipping"
            continue
        }
        $head = (& git -C $dir rev-parse --short HEAD).Trim()
        if ($head -eq $b.pinned) {
            Write-Ok "$($b.name): unchanged ($head)"
            continue
        }
        $pattern = "(?ms)(-\s+name:\s*$([regex]::Escape($b.name))\b.*?pinned:\s*)\S+"
        $text = [regex]::Replace($text, $pattern, "`${1}$head")
        Write-Ok "$($b.name): $($b.pinned) -> $head"
        $changed++
    }

    $today = Get-Date -Format 'yyyy-MM-dd'
    $text = [regex]::Replace($text, '(?m)^updated:\s*\S+', "updated: $today")
    Set-Content -Path $ManifestPath -Value $text -Encoding utf8 -NoNewline -ErrorAction Stop

    Write-Host ""
    if ($changed -gt 0) {
        Write-Ok "$changed pin(s) updated in repos.yml. Review and commit it."
    } else {
        Write-Ok "No pins needed updating."
    }
    exit 0
}

# --- sync mode --------------------------------------------------------------

$failed = @()
$skipped = @()

foreach ($b in $backends) {
    $dir = Join-Path $RepoRoot $b.path
    Write-Step "$($b.name)"

    if (-not (Test-Path (Join-Path $dir '.git'))) {
        if (Test-Path $dir) {
            Write-Err2 "$($b.path) exists but is not a git repo - resolve by hand"
            $failed += $b.name
            continue
        }
        Write-Ok "cloning $($b.url)"
        # full history on purpose: setuptools_scm reads tags at import time
        & git clone $b.url $dir
        if ($LASTEXITCODE -ne 0) { Write-Err2 "clone failed"; $failed += $b.name; continue }
    } else {
        & git -C $dir fetch --tags origin
        if ($LASTEXITCODE -ne 0) { Write-Warn2 "fetch failed - working offline?" }
    }

    if (-not (Test-CleanTree $dir)) {
        Write-Warn2 "working tree is dirty - leaving it alone (nothing discarded)"
        $skipped += $b.name
        continue
    }

    if ($Latest) {
        $target = $b.branch
        & git -C $dir checkout $b.branch
        if ($LASTEXITCODE -eq 0) { & git -C $dir pull --ff-only origin $b.branch }
    } else {
        $target = $b.pinned
        & git -C $dir checkout --quiet $b.pinned
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Err2 "could not check out $target"
        $failed += $b.name
        continue
    }

    $head = (& git -C $dir rev-parse --short HEAD).Trim()
    $desc = (& git -C $dir describe --tags 2>$null)
    if ([string]::IsNullOrWhiteSpace($desc)) { $desc = '(no tag)' } else { $desc = $desc.Trim() }
    Write-Ok "at $head  [$desc]"

    if (-not $Latest) {
        Write-Warn2 "detached at the pinned commit; to resume development: git -C $($b.path) checkout $($b.branch)"
    }
}

# --- editable install -------------------------------------------------------

if ($Install) {
    Write-Host ""
    Write-Step "Editable install of the backends"

    if ($env:CONDA_DEFAULT_ENV -ne 'labscript') {
        Write-Err2 "conda env is '$env:CONDA_DEFAULT_ENV', expected 'labscript'."
        Write-Err2 "Run 'conda activate labscript' first, then re-run with -Install."
        exit 1
    }

    $paths = @()
    foreach ($b in $backends) { $paths += @('-e', $b.path) }

    Push-Location $RepoRoot
    try {
        & pip install --no-build-isolation --no-deps @paths
        if ($LASTEXITCODE -ne 0) {
            Write-Err2 "pip install failed - see INSTALL.md Troubleshooting"
            exit 1
        }
        Write-Ok "installed"
    } finally {
        Pop-Location
    }
}

# --- summary ----------------------------------------------------------------

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Err2 "failed: $($failed -join ', ')"
    exit 1
}
if ($skipped.Count -gt 0) {
    Write-Warn2 "skipped (uncommitted changes): $($skipped -join ', ')"
}
Write-Ok "backends in sync"
if (-not $Install) {
    Write-Host "    next: conda activate labscript; .\bootstrap.ps1 -Install" -ForegroundColor DarkGray
}
