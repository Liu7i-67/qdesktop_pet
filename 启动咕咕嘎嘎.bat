@echo off
rem GuguGaga launcher: first run creates venv + installs deps, then starts without console.
rem Must stay UTF-8 (no BOM) with CRLF line endings. Chinese text is kept out of
rem parenthesized blocks on purpose: cmd may mis-parse multibyte bytes when a
rem block is skipped, so this script uses goto-flow instead of if-blocks.
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" goto :run

echo 首次运行，正在准备环境...
python -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :install_failed
if not exist ".venv\Scripts\pythonw.exe" goto :no_pythonw

:run
if not exist "main.py" goto :no_main
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:install_failed
echo 依赖安装失败，请检查 Python 与网络后重试。
pause
exit /b 1

:no_pythonw
echo 启动失败：未找到 .venv\Scripts\pythonw.exe
echo 请确认已安装 Python 3.10+ 并重试，或手动执行：
echo   python -m venv .venv
echo   ".venv\Scripts\python.exe" -m pip install -r requirements.txt
pause
exit /b 1

:no_main
echo 启动失败：未找到 main.py，请在项目根目录运行本启动器。
pause
exit /b 1
