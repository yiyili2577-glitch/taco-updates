@echo off
setlocal
cd /d "%~dp0"
echo This will request Administrator permission and open TCP 5000 only for:
echo - Windows Private network profile
echo - LocalSubnet clients
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0open_firewall_lan_test.ps1""'"
echo.
pause
