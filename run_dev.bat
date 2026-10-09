@echo off
rem ElectricTools 开发模式：后端(env Python) + 前端(Vite) 一并启动
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set MPLBACKEND=Agg
start "ElectricTools solver" cmd /k ""%~dp0env\python.exe" -m uvicorn solver.app.main:app --host 127.0.0.1 --port 8765 --reload"
timeout /t 2 >nul
cd frontend
echo [ElectricTools] 前端开发服务器启动中（默认 http://127.0.0.1:5173）
call npm run dev
