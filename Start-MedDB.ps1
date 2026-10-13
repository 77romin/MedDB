# Start a persistent local server without leaving a terminal window open.
[CmdletBinding()]
param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$meddbWorkspace = $PSScriptRoot
$meddbRuntime = Join-Path $meddbWorkspace '.run'
New-Item -ItemType Directory -Path $meddbRuntime -Force | Out-Null
if ($Port -lt 1024 -or $Port -gt 65525) { throw 'Port must be between 1024 and 65525.' }

function Get-MedDBHealth([int]$CandidatePort) {
    try {
        $meddbHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$CandidatePort/api/health" -TimeoutSec 1
        if ($meddbHealth.service -eq 'nova-meddb' -and $meddbHealth.status -eq 'ready') { return $meddbHealth }
    } catch { }
    return $null
}

$meddbSelectedPort = $null
foreach ($meddbCandidatePort in $Port..($Port + 10)) {
    $meddbExistingHealth = Get-MedDBHealth $meddbCandidatePort
    if ($null -ne $meddbExistingHealth) {
        Write-Output "MedDB already running: http://127.0.0.1:$meddbCandidatePort/ ($($meddbExistingHealth.version))"
        return
    }
    $meddbListener = Get-NetTCPConnection -LocalPort $meddbCandidatePort -State Listen -ErrorAction SilentlyContinue
    if (-not $meddbListener) { $meddbSelectedPort = $meddbCandidatePort; break }
}
if ($null -eq $meddbSelectedPort) { throw 'No free local port found. Choose another -Port.' }

$meddbPython = Join-Path $meddbWorkspace '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $meddbPython)) {
    $meddbPython = (& python -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $meddbPython)) { throw 'Python 3.9+ is required.' }
}
$meddbStdout = Join-Path $meddbRuntime "server-$meddbSelectedPort.log"
$meddbStderr = Join-Path $meddbRuntime "server-$meddbSelectedPort.err.log"
$meddbProcess = Start-Process -FilePath $meddbPython -ArgumentList @('-m','meddb','serve','--port',"$meddbSelectedPort") -WorkingDirectory $meddbWorkspace -WindowStyle Hidden -RedirectStandardOutput $meddbStdout -RedirectStandardError $meddbStderr -PassThru
for ($meddbAttempt = 0; $meddbAttempt -lt 40; $meddbAttempt++) {
    $meddbReady = Get-MedDBHealth $meddbSelectedPort
    if ($null -ne $meddbReady) {
        $meddbDetails = @{ pid=$meddbProcess.Id; port=$meddbSelectedPort; url="http://127.0.0.1:$meddbSelectedPort/"; version=$meddbReady.version; stdout=$meddbStdout; stderr=$meddbStderr }
        $meddbDetails | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $meddbRuntime 'server.json') -Encoding UTF8
        Write-Output "MedDB ready: $($meddbDetails.url) ($($meddbReady.version))"
        return
    }
    if ($meddbProcess.HasExited) { throw "MedDB exited. Check $meddbStderr" }
    Start-Sleep -Milliseconds 500
}
throw "MedDB is still starting. Check $meddbStdout and $meddbStderr"
