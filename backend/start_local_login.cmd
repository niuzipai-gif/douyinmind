@echo off
setlocal
cd /d "%~dp0"
uv run python -m app.local_login
if errorlevel 1 pause
