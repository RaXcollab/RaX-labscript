# Locate a conda installation and the python.exe of a named env, without
# hardcoding a user profile or a distribution name.
#
# Collaborators fork this repo onto machines where conda may be Miniconda or
# Anaconda, per-user or system-wide, under any username. Anything that needs an
# interpreter should dot-source this and call Get-CondaEnvPython.
#
# Resolution order, first hit wins:
#   1. $env:CONDA_EXE            - set by conda activate / conda init
#   2. `conda info --base`       - conda on PATH
#   3. common install locations  - unactivated shells
#
# Returns $null when nothing is found. Callers must fail open on $null rather
# than erroring, so a machine without conda simply skips the check.

function Get-CondaBase {
    if ($env:CONDA_EXE -and (Test-Path -LiteralPath $env:CONDA_EXE)) {
        # <base>\Scripts\conda.exe  ->  <base>
        return (Split-Path -Parent (Split-Path -Parent $env:CONDA_EXE))
    }

    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try {
        $base = (& conda info --base 2>$null)
        if ($LASTEXITCODE -eq 0 -and $base) {
            $base = ($base | Select-Object -First 1).Trim()
            if ($base -and (Test-Path -LiteralPath $base)) { return $base }
        }
    } catch {
        # conda not on PATH; fall through to the location scan
    } finally {
        $ErrorActionPreference = $prev
    }

    $candidates = @(
        (Join-Path $env:USERPROFILE 'miniconda'),
        (Join-Path $env:USERPROFILE 'miniconda3'),
        (Join-Path $env:USERPROFILE 'anaconda3'),
        (Join-Path $env:USERPROFILE 'Miniforge3'),
        (Join-Path $env:LOCALAPPDATA 'miniconda3'),
        (Join-Path $env:LOCALAPPDATA 'Continuum\miniconda3'),
        'C:\ProgramData\miniconda3',
        'C:\ProgramData\anaconda3'
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath (Join-Path $c 'python.exe'))) { return $c }
    }

    return $null
}

function Get-CondaEnvPython {
    param([string]$EnvName = 'labscript')

    $base = Get-CondaBase
    if (-not $base) { return $null }

    # the base env itself is not under envs\
    $direct = Join-Path $base 'python.exe'
    $inEnv  = Join-Path $base "envs\$EnvName\python.exe"

    if (Test-Path -LiteralPath $inEnv) { return $inEnv }
    if ($EnvName -eq 'base' -and (Test-Path -LiteralPath $direct)) { return $direct }
    return $null
}
