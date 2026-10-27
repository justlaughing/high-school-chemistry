@echo off
chcp 65001 >nul
set "CHEM_BANK_SCRIPT=%~dp002_设定层\题库维护\serve.py"
set "CHEM_BANK_PYTHONW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%CHEM_BANK_PYTHONW%" (
    start "" "%CHEM_BANK_PYTHONW%" "%CHEM_BANK_SCRIPT%"
    exit /b
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%CHEM_BANK_SCRIPT%"
    exit /b
)
where python.exe >nul 2>nul
if not errorlevel 1 (
    python.exe "%CHEM_BANK_SCRIPT%"
    exit /b
)
echo 未找到 Python。请使用本机已有的 Python 运行 02_设定层\题库维护\serve.py。
pause
