$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv-win\Scripts\python.exe")) {
    Write-Host "没有找到 Windows 虚拟环境 .venv-win。请先运行："
    Write-Host "  powershell -ExecutionPolicy Bypass -File backend\setup-dev-windows.ps1"
    exit 1
}

Write-Host "Celery worker 启动中，Redis broker：180.184.70.137:16379"
& ".\.venv-win\Scripts\celery.exe" -A celery_worker.celery worker --loglevel=info --pool=solo
