# Shared prelude for Claude Code hooks. Dot-source: . "$PSScriptRoot\_hook-common.ps1"
# Stdin MUST be read as UTF-8: [Console]::In decodes with the OEM code page (IBM437),
# which corrupts multi-byte characters in the JSON payload and broke ConvertFrom-Json
# silently (markers skipped, gate failed open). Output likewise forced to UTF-8.
Set-StrictMode -Off
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

function Read-HookInput {
    # Returns the parsed stdin JSON, or $null on empty/malformed input.
    # Callers decide fail-open vs fail-closed explicitly on $null.
    try {
        $reader = New-Object IO.StreamReader([Console]::OpenStandardInput(), [Text.Encoding]::UTF8)
        $raw = $reader.ReadToEnd()
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        return ($raw | ConvertFrom-Json -ErrorAction Stop)
    } catch { return $null }
}

function Get-MarkerPath([string]$kind, [string]$sessionId) {
    # Marker = empty file whose mtime is the event time. Session-scoped by id.
    if ([string]::IsNullOrEmpty($sessionId) -or -not $env:TEMP) { return $null }
    return (Join-Path $env:TEMP ("claude-{0}-{1}" -f $kind, $sessionId))
}

function Set-Marker([string]$kind, [string]$sessionId) {
    $p = Get-MarkerPath $kind $sessionId
    if (-not $p) { return }
    # -Force intentionally recreates the file so mtime advances on every event.
    try { New-Item -ItemType File -Force -Path $p | Out-Null } catch {}
}

function Get-MarkerTime([string]$kind, [string]$sessionId) {
    $p = Get-MarkerPath $kind $sessionId
    if (-not $p) { return $null }
    return (Get-Item -LiteralPath $p -ErrorAction SilentlyContinue).LastWriteTimeUtc
}

function Remove-SessionMarkers([string]$sessionId) {
    # SessionStart (startup|resume|clear) wipes this session's markers so a
    # resumed session cannot inherit yesterday's edit/audit state.
    if ([string]::IsNullOrEmpty($sessionId) -or -not $env:TEMP) { return }
    try {
        Get-ChildItem -Path $env:TEMP -Filter ("claude-*-{0}" -f $sessionId) -File -ErrorAction Stop |
            Remove-Item -Force -ErrorAction SilentlyContinue
    } catch {}
}
