@echo off
setlocal
cd /d "%~dp0"
set "LICENSE_HOST=127.0.0.1"
set "LICENSE_PORT=5000"
set "ALLOW_LAN_TEST=0"
echo ========================================
echo TACO License Server 2.0 - Local Test
echo http://127.0.0.1:5000
echo ========================================
if not exist ".license_venv\Scripts\python.exe" (
  echo ERROR: .license_venv not found.
  echo Please create/install the license server venv first.
  pause
  exit /b 1
)
".license_venv\Scripts\python.exe" app.py
pause
