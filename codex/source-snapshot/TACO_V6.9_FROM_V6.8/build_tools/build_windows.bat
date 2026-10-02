@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."
set PYTHONUTF8=1
set "LOGDIR=build_logs"
set "LOGFILE=%LOGDIR%\build_windows_latest.log"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

> "%LOGFILE%" echo ===== TACO V6.9.0 Windows Production Build =====
>>"%LOGFILE%" echo Started: %DATE% %TIME%
>>"%LOGFILE%" echo Root: %CD%

echo ============================================================
echo   TACO V6.9.0 Windows Production Build
echo ============================================================
echo.
echo This window will stay open even if the build fails.
echo Build log: %CD%\%LOGFILE%
echo.

rem ------------------------------------------------------------
rem 1. Find a Windows Python launcher/interpreter.
rem ------------------------------------------------------------
set "BOOTSTRAP_PY="
where py >nul 2>nul
if not errorlevel 1 set "BOOTSTRAP_PY=py -3"
if not defined BOOTSTRAP_PY (
  where python >nul 2>nul
  if not errorlevel 1 set "BOOTSTRAP_PY=python"
)
if not defined BOOTSTRAP_PY (
  echo [ERROR] Python 3 was not found.
  echo Install Python 3 for Windows, and enable the Python Launcher ^(py^) or PATH.
  >>"%LOGFILE%" echo ERROR: Python 3 was not found.
  goto :fail
)

echo [1/7] Checking Python...
%BOOTSTRAP_PY% --version
if errorlevel 1 goto :fail
%BOOTSTRAP_PY% --version >>"%LOGFILE%" 2>&1

rem ------------------------------------------------------------
rem 2. Use a dedicated build venv so we do not depend on Erp_app .venv.
rem ------------------------------------------------------------
if not exist ".build_venv\Scripts\python.exe" (
  echo [2/7] Creating dedicated build environment .build_venv ...
  echo       First build may take several minutes.
  %BOOTSTRAP_PY% -m venv ".build_venv" >>"%LOGFILE%" 2>&1
  if errorlevel 1 goto :show_log_fail
) else (
  echo [2/7] Reusing existing .build_venv ...
)
set "PYTHON_EXE=%CD%\.build_venv\Scripts\python.exe"

rem ------------------------------------------------------------
rem 3. Install build dependencies.
rem ------------------------------------------------------------
echo [3/7] Installing / updating build dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :show_log_fail
"%PYTHON_EXE%" -m pip install -r "desktop_app\requirements-desktop.txt" >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :show_log_fail

rem ------------------------------------------------------------
rem 4. Validate the already-deployed public keys. Desktop builds never access private keys.
rem ------------------------------------------------------------
echo [4/7] Validating License / Update public keys...
call "build_tools\prepare_security_keys.bat" >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :show_log_fail

rem ------------------------------------------------------------
rem 5. Clean only build output; never touch ProgramData or user data.
rem ------------------------------------------------------------
echo [5/7] Cleaning previous build output...
if exist "dist\TACO" rmdir /s /q "dist\TACO"
if exist "dist\TACOUpdater.exe" del /q "dist\TACOUpdater.exe"
if not exist "dist" mkdir "dist"

rem ------------------------------------------------------------
rem 6. Build TACO.exe and TACOUpdater.exe.
rem ------------------------------------------------------------
set TACO_BUILD_MODE=prod
echo [6/7] Building TACO.exe with PyInstaller...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --log-level INFO --distpath "dist" --workpath "build\pyinstaller" "build_tools\TACO.spec" >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :show_log_fail

echo       Building TACOUpdater.exe...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --log-level INFO --distpath "dist" --workpath "build\pyinstaller_updater" "build_tools\TACOUpdater.spec" >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :show_log_fail

if not exist "dist\TACO\TACO.exe" (
  >>"%LOGFILE%" echo ERROR: PyInstaller returned success but dist\TACO\TACO.exe was not found.
  goto :show_log_fail
)
if not exist "dist\TACOUpdater.exe" (
  >>"%LOGFILE%" echo ERROR: PyInstaller returned success but dist\TACOUpdater.exe was not found.
  goto :show_log_fail
)
copy /y "dist\TACOUpdater.exe" "dist\TACO\TACOUpdater.exe" >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :show_log_fail
copy /y "desktop_app\VERSION" "dist\TACO\BUILD_VERSION.txt" >>"%LOGFILE%" 2>&1
if errorlevel 1 goto :show_log_fail

rem ------------------------------------------------------------
rem 7. Success.
rem ------------------------------------------------------------
echo [7/7] Verifying output...
for %%F in ("dist\TACO\TACO.exe" "dist\TACO\TACOUpdater.exe") do (
  if not exist %%F goto :show_log_fail
)
>>"%LOGFILE%" echo Completed: %DATE% %TIME%
>>"%LOGFILE%" echo SUCCESS

echo.
echo ============================================================
echo BUILD COMPLETE
echo ============================================================
echo TACO.exe:
echo   %CD%\dist\TACO\TACO.exe
echo TACOUpdater.exe:
echo   %CD%\dist\TACO\TACOUpdater.exe
echo.
echo IMPORTANT: PRIVATE KEYS were NOT copied into dist.
echo.
echo Press any key to close this window.
pause >nul
exit /b 0

:show_log_fail
echo.
echo ============================================================
echo BUILD FAILED - showing the last part of the log
 echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path '%LOGFILE%') { Get-Content -Path '%LOGFILE%' -Tail 80 }"
goto :fail_pause

:fail
echo.
echo ============================================================
echo BUILD FAILED
 echo ============================================================

:fail_pause
echo.
echo Full log:
echo   %CD%\%LOGFILE%
echo.
echo Please take a screenshot of this window, or send build_windows_latest.log.
echo Press any key to close this window.
pause >nul
exit /b 1
