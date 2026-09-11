@echo off
rem deepAStock one-click local start (no Docker)
rem starts backend + frontend, auto picks free ports on conflict
chcp 65001 >nul
cd /d "%~dp0"
python -X utf8 backend\scripts\dev_up.py
pause