$ErrorActionPreference = "Stop"
$StudioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentRoot = (Resolve-Path (Join-Path $StudioRoot "..\..")).Path
$BackendScript = Join-Path $AgentRoot "pipeline\studio_api.py"
if (-not (Test-Path -LiteralPath $BackendScript)) { throw "Không tìm thấy render backend: $BackendScript" }

# Stop only the previous studio processes/listeners so stale code cannot keep serving port 8787.
$StateFile = Join-Path $StudioRoot ".studio-processes.json"
if (Test-Path -LiteralPath $StateFile) {
    try {
        $OldState = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        @($OldState.backend_pid, $OldState.frontend_pid) | Where-Object { $_ } | ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    } catch { }
}
foreach ($Port in 8787, 4173) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

$Backend = Start-Process -FilePath "python" -ArgumentList @($BackendScript) -WorkingDirectory $AgentRoot -WindowStyle Hidden -PassThru
$Frontend = Start-Process -FilePath "npm.cmd" -ArgumentList @("run","dev","--","--port","4173") -WorkingDirectory $StudioRoot -WindowStyle Hidden -PassThru

$State = @{ backend_pid=$Backend.Id; frontend_pid=$Frontend.Id; url="http://127.0.0.1:4173"; started_at=(Get-Date).ToString("o") }
$State | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding utf8
for ($i=0; $i -lt 20; $i++) {
    try {
        $Health = Invoke-RestMethod "http://127.0.0.1:8787/health" -TimeoutSec 1
        if ($Health.ok) { break }
    } catch { Start-Sleep -Milliseconds 300 }
}
if (-not $Health.ok) { throw "Render backend không khởi động được tại cổng 8787" }
Start-Sleep -Seconds 1
Start-Process "http://127.0.0.1:4173"
Write-Host "AI Clip Studio đang chạy tại http://127.0.0.1:4173"
