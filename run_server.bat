@echo off
rem ElectricTools 后端（使用根目录 env 内嵌 Python）
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set MPLBACKEND=Agg
echo [ElectricTools] 启动求解服务 http://127.0.0.1:8765
"%~dp0env\python.exe" -m uvicorn solver.app.main:app --host 127.0.0.1 --port 8765 %*
