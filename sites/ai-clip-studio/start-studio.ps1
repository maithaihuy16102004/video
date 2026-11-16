$ErrorActionPreference = "Stop"
$StudioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentRoot = (Resolve-Path (Join-Path $StudioRoot "..\..")).Path
$BackendScript = Join-Path $AgentRoot "pipeline\studio_api.py"
if (-not (Test-Path -LiteralPath $BackendScript)) { throw "Không tìm thấy render backend: $BackendScript" }
$ProductionModule = "ai_clip_studio.server"

# Stop only the previous studio processes/listeners so stale code cannot keep serving port 8787.
$StateFile = Join-Path $StudioRoot ".studio-processes.json"
if (Test-Path -LiteralPath $StateFile) {
    try {
        $OldState = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        @($OldState.backend_pid, $OldState.production_pid, $OldState.frontend_pid) | Where-Object { $_ } | ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    } catch { }
}
foreach ($Port in 8787, 8788, 3000) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

$Backend = Start-Process -FilePath "python" -ArgumentList @($BackendScript) -WorkingDirectory $AgentRoot -WindowStyle Hidden -PassThru
$Production = Start-Process -FilePath "python" -ArgumentList @("-m",$ProductionModule,"--port","8788") -WorkingDirectory $AgentRoot -WindowStyle Hidden -PassThru
$Frontend = Start-Process -FilePath "npm.cmd" -ArgumentList @("run","dev","--","--host","127.0.0.1","--port","3000") -WorkingDirectory $StudioRoot -WindowStyle Hidden -PassThru

$State = @{ backend_pid=$Backend.Id; production_pid=$Production.Id; frontend_pid=$Frontend.Id; url="http://127.0.0.1:3000"; started_at=(Get-Date).ToString("o") }
$State | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding utf8
$RenderReady = $false
$ProductionReady = $false
for ($i=0; $i -lt 20; $i++) {
    try {
        $RenderHealth = Invoke-RestMethod "http://127.0.0.1:8787/health" -TimeoutSec 1
        $RenderReady = [bool]$RenderHealth.ok
    } catch { Start-Sleep -Milliseconds 300 }
    try {
        $ProductionHealth = Invoke-RestMethod "http://127.0.0.1:8788/health" -TimeoutSec 1
        $ProductionReady = ([bool]$ProductionHealth.ok) -or ($ProductionHealth.status -eq "ok")
    } catch { Start-Sleep -Milliseconds 300 }
    if ($RenderReady -and $ProductionReady) { break }
}
if (-not $RenderReady) { throw "Render backend không khởi động được tại cổng 8787" }
if (-not $ProductionReady) { throw "Production/Preflight backend không khởi động được tại cổng 8788" }
$FrontendReady = $false
for ($i=0; $i -lt 30; $i++) {
    try {
        $FrontendResponse = Invoke-WebRequest "http://127.0.0.1:3000" -TimeoutSec 2 -UseBasicParsing
        if ($FrontendResponse.StatusCode -ge 200 -and $FrontendResponse.StatusCode -lt 500) {
            $FrontendReady = $true
            break
        }
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $FrontendReady) { throw "Frontend không khởi động được tại cổng 3000" }
Start-Process "http://127.0.0.1:3000"
Write-Host "AI Clip Studio đang chạy tại http://127.0.0.1:3000 (render 8787, preflight 8788)"
