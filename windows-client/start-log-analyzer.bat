@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0dist\LogAnalyzerClient.exe" (
  start "" "%~dp0dist\LogAnalyzerClient.exe"
  exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "%~dp0log_analyzer_client.py"
) else (
  python "%~dp0log_analyzer_client.py"
)
