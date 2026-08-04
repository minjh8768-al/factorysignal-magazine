@echo off
REM Daily draft job for Task Scheduler. ASCII only - see project CLAUDE.md.
REM Generates one draft per category and runs the fact-check. Does NOT publish.
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher "py" not found.
  exit /b 1
)

py -3 "tools\daily.py" %*
exit /b %errorlevel%
