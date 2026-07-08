$j = [Console]::In.ReadToEnd() | ConvertFrom-Json
if ($j.stop_hook_active) { exit 0 }   # fire at most once per turn-chain
$sid = $j.session_id
$edited  = Test-Path (Join-Path $env:TEMP "claude-device-edit-$sid")
$audited = Test-Path (Join-Path $env:TEMP "claude-audit-ran-$sid")
if ($edited -and -not $audited) {
  [Console]::Error.WriteLine("Gate: user_devices/ or blacs/ files were edited this session with no blacs-expert audit. Run the audit (Agent: blacs-expert, scope = blast radius) or state explicitly to the user why it is not needed.")
  exit 2   # Stop-hook exit 2: reason fed back to Claude, turn continues
}
exit 0
