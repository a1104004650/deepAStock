@echo off
chcp 65001 >nul
title deepAStock 深度A股交易 - 启动器
echo ============================================
echo   deepAStock 深度A股交易  一键启动
echo ============================================
echo [1] 启动后端 (FastAPI 8000)
echo [2] 启动前端 (Vite 5173)
echo [3] 全部停止
echo [4] 查看状态
echo [5] 初始化数据库
echo [0] 退出
echo ============================================
set /p choice=请选择:

if "%choice%"=="1" (
  cd /d "%~dp0backend"
  python scripts\run_server.py start
  goto end
)
if "%choice%"=="2" (
  cd /d "%~dp0backend"
  python scripts\run_frontend.py start
  goto end
)
if "%choice%"=="3" (
  cd /d "%~dp0backend"
  python scripts\run_server.py stop
  python scripts\run_frontend.py stop
  goto end
)
if "%choice%"=="4" (
  cd /d "%~dp0backend"
  python scripts\run_server.py status
  python scripts\run_frontend.py status
  goto end
)
if "%choice%"=="5" (
  cd /d "%~dp0backend"
  python -m scripts.init_db
  goto end
)
:end
echo.
pause