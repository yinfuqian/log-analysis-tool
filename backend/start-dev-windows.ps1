$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv-win\Scripts\python.exe")) {
    Write-Host "没有找到 Windows 虚拟环境 .venv-win。请先运行："
    Write-Host "  powershell -ExecutionPolicy Bypass -File backend\setup-dev-windows.ps1"
    exit 1
}

$env:FLASK_ENV = "development"
$env:PYTHONUNBUFFERED = "1"

Write-Host "后端启动中：http://127.0.0.1:5000"
Write-Host "日志文件：$PSScriptRoot\app\logs\app.log"
Write-Host ""

& ".\.venv-win\Scripts\python.exe" app.py
