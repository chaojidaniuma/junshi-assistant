@echo off
rem 军师助手 - 一键打包 EXE
chcp 65001 >nul
cd /d "%~dp0\.."

echo [1/2] 安装依赖（wxauto4 需从 GitHub 安装）
pip install "git+https://github.com/zhengheng077/wxauto4.git" pyinstaller

echo [2/2] 打包
python -m PyInstaller --noconfirm --onefile --windowed ^
  --name "junshi-assistant" --collect-all wxauto4 --add-data "kb;kb" ui\gui.py

echo.
echo 完成：dist\junshi-assistant.exe
echo 使用前请复制 config.example.json 为 config.json 并填写配置。
pause
