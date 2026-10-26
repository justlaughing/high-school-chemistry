@echo off
chcp 65001 >nul
set "CHEM_PILOT_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CHEM_PILOT_PYTHON%" (
    "%CHEM_PILOT_PYTHON%" "%~dp0serve.py"
    exit /b
)
where python.exe >nul 2>nul
if not errorlevel 1 (
    python.exe "%~dp0serve.py"
    exit /b
)
echo 未找到 Python。请在已有 Python 环境中运行本目录的 serve.py。
pause
