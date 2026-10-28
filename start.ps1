$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '请先按照 README.md 创建虚拟环境并安装依赖。'
}
& $pythonPath -m backend.ollama_service
if ($LASTEXITCODE -ne 0) { throw 'Ollama could not be started. See the error above.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'frontend\dist\index.html'))) {
    Push-Location (Join-Path $PSScriptRoot 'frontend')
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw '前端构建失败，请先运行 npm install。' }
    } finally { Pop-Location }
}
Write-Host 'BrainStorm: http://127.0.0.1:8000' -ForegroundColor Cyan
Write-Host '请确保 Ollama 已启动。按 Ctrl+C 退出。'
& $pythonPath -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
