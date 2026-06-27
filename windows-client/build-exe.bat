@echo off
setlocal
cd /d "%~dp0"

copy /Y client_build_info.py client_build_info.py.bak >nul
python update_build_info.py
if %errorlevel% neq 0 (
  echo.
  echo Failed to update client build info.
  if exist client_build_info.py.bak copy /Y client_build_info.py.bak client_build_info.py >nul
  if exist client_build_info.py.bak del /Q client_build_info.py.bak
  exit /b %errorlevel%
)

python -m PyInstaller --onefile --windowed --name LogAnalyzerClient log_analyzer_client.py
if %errorlevel% neq 0 (
  echo.
  echo Build failed. Install dependencies first:
  echo python -m pip install -r requirements.txt
  if exist client_build_info.py.bak copy /Y client_build_info.py.bak client_build_info.py >nul
  if exist client_build_info.py.bak del /Q client_build_info.py.bak
  exit /b %errorlevel%
)

if exist client_build_info.py.bak del /Q client_build_info.py.bak

echo.
echo Build complete:
echo %~dp0dist\LogAnalyzerClient.exe
