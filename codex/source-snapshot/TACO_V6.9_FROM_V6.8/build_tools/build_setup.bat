@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "ROOT=%~dp0.."
cd /d "%ROOT%"

set "VERSION=6.9.0"
if exist "%ROOT%\desktop_app\VERSION" set /p VERSION=<"%ROOT%\desktop_app\VERSION"
set "SETUP_NAME=TACO_Setup_%VERSION%.exe"
set "ISS_FILE=%ROOT%\installer\TACO_V690.iss"

if not exist "build_logs" mkdir "build_logs"
set "LOG=%ROOT%\build_logs\build_setup_latest.log"
>"%LOG%" echo TACO V%VERSION% Setup Build - %date% %time%

call :log "============================================================"
call :log " TACO V%VERSION% Setup Build"
call :log "============================================================"
call :log "Project root: %ROOT%"

set "DIST_READY=0"
set "DIST_VERSION="
if exist "%ROOT%\dist\TACO\TACO.exe" if exist "%ROOT%\dist\TACO\BUILD_VERSION.txt" (
    set /p DIST_VERSION=<"%ROOT%\dist\TACO\BUILD_VERSION.txt"
    if "!DIST_VERSION!"=="%VERSION%" set "DIST_READY=1"
)

if "%DIST_READY%"=="1" (
    call :log "[1/4] Existing dist\TACO matches V%VERSION% - skip PyInstaller rebuild."
) else (
    if exist "%ROOT%\dist\TACO\TACO.exe" (
        call :log "[1/4] Existing dist is stale or missing BUILD_VERSION marker - rebuilding Windows app..."
    ) else (
        call :log "[1/4] dist\TACO\TACO.exe not found - building Windows app first..."
    )
    call "%ROOT%\build_tools\build_windows.bat"
    if errorlevel 1 (
        call :fail "Windows EXE build failed. Check build_windows_latest.log."
        goto :eof
    )
)

if not exist "%ROOT%\dist\TACO\TACO.exe" (
    call :fail "TACO.exe is still missing under dist\TACO."
    goto :eof
)

call :log "[2/4] Searching for Inno Setup 6 compiler (ISCC.exe)..."
set "ISCC="
if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if defined ProgramFiles if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%I"
)
if not defined ISCC (
    call :fail "Inno Setup 6 compiler was not found."
    goto :eof
)
call :log "Found ISCC: %ISCC%"

call :log "[3/4] Preparing installer output..."
if not exist "%ROOT%\installer\Output" mkdir "%ROOT%\installer\Output"
if exist "%ROOT%\installer\Output\%SETUP_NAME%" del /q "%ROOT%\installer\Output\%SETUP_NAME%" >nul 2>&1

if not exist "%ISS_FILE%" (
    call :fail "Installer script not found: %ISS_FILE%"
    goto :eof
)

call :log "[4/4] Compiling %SETUP_NAME%..."
"%ISCC%" "%ISS_FILE%" >>"%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    call :fail "Inno Setup compilation failed with exit code %RC%."
    goto :eof
)

if not exist "%ROOT%\installer\Output\%SETUP_NAME%" (
    call :fail "Compiler returned success but %SETUP_NAME% was not found."
    goto :eof
)

call :log ""
call :log "============================================================"
call :log " SETUP BUILD COMPLETE"
call :log "============================================================"
call :log "Output:"
call :log "  %ROOT%\installer\Output\%SETUP_NAME%"
call :log ""
call :log "Company data under C:\ProgramData\TACO is NOT packaged or deleted."
call :log ""
echo.
echo Press any key to close this window...
pause >nul
exit /b 0

:log
echo %~1
echo %~1>>"%LOG%"
exit /b 0

:fail
call :log ""
call :log "[ERROR] %~1"
call :log "Log file: %LOG%"
echo.
echo Build failed. This window will stay open so you can read the error.
echo Log: "%LOG%"
echo.
pause
exit /b 1
