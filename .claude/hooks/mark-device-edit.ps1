$j = [Console]::In.ReadToEnd() | ConvertFrom-Json
$p = $j.tool_input.file_path
if ($p -and ($p -match 'user_devices' -or $p -match '[\\/]blacs[\\/]')) {
  $null = New-Item -ItemType File -Force -Path (Join-Path $env:TEMP "claude-device-edit-$($j.session_id)")
}
exit 0
