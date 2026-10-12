# 공개 샘플 3건(C01, C03, C10)을 API 키 없이 로컬 Ollama로 돌린다.
# nova-starter 폴더에서 실행:  powershell -ExecutionPolicy Bypass -File local\run_samples.ps1
#   -Agent baseline (기본값) | meddb
#   case.md 는 samples\C01.md, samples\C03.md, samples\C10.md 로 저장해 둔다.
param(
    [string]$Agent = "baseline",
    [string[]]$Cases = @("C01", "C03", "C10")
)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$answers = @{ "C01" = "수면제(졸피뎀) 의존 (추정)"; "C03" = "체질성 성장지연 (추정)"; "C10" = "그레이브스병 (추정)" }

try { Invoke-RestMethod http://localhost:11434/api/tags | Out-Null }
catch { Write-Host "Ollama가 꺼져 있습니다. 먼저 Ollama를 실행하세요."; exit 1 }

New-Item -ItemType Directory -Force local\cases\samples, local\out | Out-Null
foreach ($c in $Cases) {
    $md = "samples\$c.md"
    if (-not (Test-Path $md)) { Write-Host "$md 없음 - 건너뜀"; continue }
    python tools\case_md_to_json.py $md --id $c --answer $answers[$c] -o "local\cases\samples\$c.json"
    Write-Host "`n==================== $c ($Agent) ===================="
    python local\local_run.py --case "local\cases\samples\$c.json" --agent $Agent 2>&1 |
        Tee-Object -FilePath "local\out\${c}_${Agent}.txt"
}
Write-Host "`n완료. 화면 기록: local\out\*_$Agent.txt / 상세 JSON: local\out\*_$Agent.json"
