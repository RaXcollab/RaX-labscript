$j = [Console]::In.ReadToEnd() | ConvertFrom-Json
$null = New-Item -ItemType File -Force -Path (Join-Path $env:TEMP "claude-audit-ran-$($j.session_id)")
exit 0
