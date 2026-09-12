@echo off
cd /d "%~dp0"
if exist "dist\Shixiang.exe" (
    start "" "dist\Shixiang.exe"
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" app.py
    exit /b
)
python app.py
if errorlevel 1 pause
