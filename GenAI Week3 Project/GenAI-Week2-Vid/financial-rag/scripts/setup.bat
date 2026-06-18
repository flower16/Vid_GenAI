@echo off
REM One-shot environment setup for the Financial RAG project (Windows CMD).
REM Usage:  scripts\setup.bat
setlocal
cd /d "%~dp0.."

echo Project root: %CD%

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found on PATH. Install Python 3.11+ from https://www.python.org/downloads/
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment (.venv)...
    python -m venv .venv
) else (
    echo .venv already exists - reusing it.
)

echo Installing dependencies (this can take a few minutes)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env from template - EDIT IT and set OPENAI_API_KEY.
) else (
    echo .env already exists - leaving it untouched.
)

echo.
echo Setup complete.
echo Next steps:
echo   1. Edit .env and set OPENAI_API_KEY=sk-...
echo   2. .venv\Scripts\activate.bat
echo   3. python run_experiments.py    ^(or: streamlit run src\app.py^)
endlocal
