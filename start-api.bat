@echo off
title Ops Report API (port 8000)
cd /d "C:\Users\29046\Documents\Trae-CN\temp_20261029_01\ecom-ops-automation"
set "PYTHONPATH=src"

set "PY=E:\python\python.exe"
if not exist "%PY%" set "PY=python"

echo ==========================================
echo   Ops Report API starting ...
echo   URL: http://localhost:8000
echo   Keep this window OPEN. Closing stops it.
echo ==========================================
echo.

"%PY%" -m ops_automation.api

echo.
echo [Service exited] See messages above.
pause
