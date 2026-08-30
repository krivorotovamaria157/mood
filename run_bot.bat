@echo off
REM Launcher for the moodbot Telegram bot.
REM
REM Working directory matters: the bot reads .env and creates moodbot.sqlite3
REM relative to it. Task Scheduler does NOT set it for you, hence the cd below.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtualenv not found. Run:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -e ".[dev]"
    exit /b 1
)

if not exist ".env" (
    echo .env not found. Copy .env.example to .env and fill in TELEGRAM_BOT_TOKEN.
    exit /b 2
)

set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" -m moodbot
exit /b %ERRORLEVEL%
