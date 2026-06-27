$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$pythonCommand = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python311 = py -3.11 --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = "py -3.11"
    }
}

if (-not $pythonCommand) {
    Write-Host "未检测到 Python 3.11。当前项目建议使用 Python 3.11。"
    Write-Host "请先安装 Python 3.11，然后重新运行："
    Write-Host "  powershell -ExecutionPolicy Bypass -File backend\setup-dev-windows.ps1"
    exit 1
}

if (Test-Path ".venv-win") {
    Write-Host "已存在 .venv-win，跳过创建。"
} else {
    Write-Host "正在创建 Windows 虚拟环境 .venv-win..."
    Invoke-Expression "$pythonCommand -m venv .venv-win"
}

Write-Host "正在升级 pip..."
& ".\.venv-win\Scripts\python.exe" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

Write-Host "正在安装 Windows 本地调试依赖..."
& ".\.venv-win\Scripts\python.exe" -m pip install -r requirements-windows.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

Write-Host ""
Write-Host "环境准备完成。启动后端："
Write-Host "  powershell -ExecutionPolicy Bypass -File backend\start-dev-windows.ps1"
