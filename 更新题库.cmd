@echo off
chcp 65001 >nul
set "CHEM_BANK_SCRIPT=%~dp002_设定层\试卷分类题库\题库工具\server.py"
set "CHEM_BANK_PYTHONW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%CHEM_BANK_PYTHONW%" (
    start "" "%CHEM_BANK_PYTHONW%" "%CHEM_BANK_SCRIPT%" --update --open
    exit /b
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "%CHEM_BANK_SCRIPT%" --update --open
    exit /b
)
where python.exe >nul 2>nul
if not errorlevel 1 (
    python.exe "%CHEM_BANK_SCRIPT%" --update --open
    exit /b
)
echo 未找到 Python 运行环境。可以先双击“题库首页.html”浏览最近同步的离线内容。
pause
