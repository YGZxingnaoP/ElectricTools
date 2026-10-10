@echo off
rem ============================================================
rem  ElectricTools 打包为 Windows exe（使用根目录 env 内嵌 Python）
rem    用法： build_exe.bat            打包「单文件 exe」（默认，便于分发）
rem           build_exe.bat onedir     打包「文件夹版」（启动更快）
rem  产物：   单文件 → dist_exe\ElectricTools.exe
rem            文件夹 → dist_exe\ElectricTools\ElectricTools.exe
rem  注意：   exe 首次运行会在**自己所在目录**生成 config.local.yaml 与 storage\ 存档
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
set PYTHONUTF8=1
set MPLBACKEND=Agg
set MODE=onefile
set EXTRA=--onefile
if /i "%~1"=="onedir" ( set MODE=onedir & set EXTRA= )

echo [1/4] 构建前端（frontend\dist）...
pushd frontend
call npm run build
if errorlevel 1 ( echo   前端构建失败 & popd & pause & exit /b 1 )
popd

echo [2/4] 检查 PyInstaller...
"%~dp0env\python.exe" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo   未安装，正在安装...
  "%~dp0env\python.exe" -m pip install pyinstaller
  if errorlevel 1 ( echo   安装失败 & pause & exit /b 1 )
)

echo [3/4] 清理旧产物...
if exist dist_exe rmdir /s /q dist_exe
if exist build_exe rmdir /s /q build_exe

echo [4/4] PyInstaller 打包（模式：%MODE%，首次约 2-5 分钟）...
"%~dp0env\python.exe" -m PyInstaller --noconfirm --clean !EXTRA! ^
  --name ElectricTools ^
  --distpath dist_exe --workpath build_exe ^
  --console ^
  --add-data "frontend\dist;frontend\dist" ^
  --add-data "config.example.yaml;." ^
  --collect-all lcapy ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import uvicorn.lifespan.off ^
  --hidden-import websockets ^
  --hidden-import wsproto ^
  --hidden-import yaml ^
  launcher.py
if errorlevel 1 ( echo   打包失败 & pause & exit /b 1 )

echo.
if /i "%MODE%"=="onefile" (
  echo  完成： %~dp0dist_exe\ElectricTools.exe      ^(双击运行^)
) else (
  echo  完成： %~dp0dist_exe\ElectricTools\ElectricTools.exe      ^(双击运行^)
)
echo  也可以直接用： env\python.exe launcher.py
pause
