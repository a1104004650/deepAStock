@echo off
rem deepAStock one-click local start (no Docker)
rem starts backend + frontend, auto picks free ports on conflict
chcp 65001 >nul
cd /d "%~dp0"
"C:\veighna_studio\python.exe" -X utf8 backend\scripts\dev_up.py
if errorlevel 1 (
  echo.
  echo [START FAILED] dev_up.py exited with code %errorlevel%
  echo Check C:\aiStock\backend\data\logs\dev_backend_stderr.log and dev_frontend_stderr.log
  pause
  exit /b %errorlevel%
)
pause
