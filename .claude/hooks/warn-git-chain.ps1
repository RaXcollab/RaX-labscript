# PreToolUse (Bash, if "Bash(git *)"): HARD gates on the three risky-git classes
# from the 22-session retrospective (pattern 2) — exit 2 cancels the call and
# feeds stderr back to Claude (same pattern as the rm-guard in settings.json).
#   G1: &&-chained git mutation — the c3999c1 collision class
#   G2: broad staging (add -A/-u/./glob) — stages other sessions' hunks
#   G3: non-v* tag touching a backend repo — setuptools_scm parses git describe
#       at import; a stray tag crashes `import labscript_utils` = lab-wide outage
# Known gaps (accepted): PowerShell-tool git calls not covered; a literal "&&"
# inside a commit-message string false-positives; `git tag -m "msg" name` hides
# the name from G3's option skipper (-a/-s/-f forms are handled).
. "$PSScriptRoot\_hook-common.ps1"

$in = Read-HookInput
if (-not $in) { exit 0 }
$cmd = $in.tool_input.command
if (-not $cmd) { exit 0 }

function Deny([string]$msg) { [Console]::Error.WriteLine($msg); exit 2 }

# --- G1: chained mutation
$mutation = '(?i)git\s+(-C\s+\S+\s+)?(commit|push|reset|restore|checkout|switch|rebase|merge|revert|cherry-pick|tag|stash|clean|am)\b'
if ($cmd -match '&&' -and $cmd -match $mutation) {
    Deny "GIT GUARD: this chained command contains a git mutation ('$($Matches[0].Trim())'). Lab rule: ONE git mutation per shell call - concurrent sessions can change staging/branch state between chained commands. Inspect state (git status / git diff --cached) in its own call, then run the mutation alone. Re-issue as separate calls."
}

# --- G2: broad staging on a mixed tree
if ($cmd -match '(?i)git\s+(-C\s+\S+\s+)?add\s') {
    $addArgs = ($cmd -replace '(?i)^.*?git\s+(-C\s+\S+\s+)?add\s+', '')
    if ($addArgs -match '(^|\s)(-A|--all|-u|--update|\.)(\s|$)' -or $addArgs -match '\*') {
        Deny "GIT GUARD: broad staging ('git add $($addArgs.Trim())') on a mixed tree stages other sessions' hunks (calibration_data.json, concurrent campaign files). Stage files BY NAME, then inspect git diff --cached before committing."
    }
}

# --- G3: non-v* tag creation in a backend repo
if ($cmd -match '(?i)git\s+(-C\s+(?<repo>\S+)\s+)?tag\s+((-[asf]|--force|--annotate|--sign)\s+)*(?<tag>[^-\s]\S*)') {
    $tagName = $Matches['tag']
    $repoRef = "$($Matches['repo']) $($in.cwd)"
    if ($tagName -notmatch '^v\d' -and $repoRef -match '(?i)[\\/](blacs|labscript-devices|labscript-utils)([\\/]|\s|$)') {
        Deny "GIT GUARD: creating tag '$tagName' in a backend repo. setuptools_scm parses git describe at IMPORT time - a non-v* tag reachable from HEAD crashes import labscript_utils (BLACS/RunManager cannot start; lab-wide outage, docs/stable-snapshot-2026-06-09.md). Pin backend baselines by COMMIT HASH. A real release tag must match v<semver> and needs explicit user approval."
    }
}
exit 0
