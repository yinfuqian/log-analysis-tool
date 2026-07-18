REM start-log-analyzer 脚本负责 Windows 客户端的启动或构建流程。
@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0dist\FaultAnalyzerClient.exe" (
  start "" "%~dp0dist\FaultAnalyzerClient.exe"
  exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "%~dp0log_analyzer_client.py"
) else (
  python "%~dp0log_analyzer_client.py"
)
