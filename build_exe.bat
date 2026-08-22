@echo off
rem ============================================================
rem  狗头助手 · Windows 桌面版打包脚本
rem  产物：dist\狗头助手.exe（单文件，双击即用）
rem ============================================================
setlocal
cd /d "%~dp0"

echo [1/3] 安装打包依赖...
python -m pip install --quiet pyinstaller || goto :err

set EXTRA=
python -c "import wxauto4" >nul 2>&1
if %errorlevel%==0 set EXTRA=--collect-all wxauto4

echo [2/3] 开始打包（约 1-3 分钟）...
python -m PyInstaller --noconfirm --onefile --windowed ^
  --name "狗头助手" ^
  %EXTRA% ^
  --collect-submodules junshi_harness ^
  --collect-submodules junshi_domain ^
  --collect-submodules providers ^
  --collect-submodules adapters ^
  --collect-submodules interfaces ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import websockets ^
  --add-data "kb\references;kb\references" ^
  --add-data "interfaces\web\index.html;interfaces\web" ^
  --add-data "config.example.json;." ^
  desktop.py || goto :err

echo.
echo [3/3] 完成！产物: dist\狗头助手.exe（双击运行）
pause
exit /b 0

:err
echo.
echo 打包失败，请检查上方报错信息。
pause
exit /b 1
