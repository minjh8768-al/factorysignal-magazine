@echo off
REM Preview server for drafts and articles. ASCII only - see project CLAUDE.md.
setlocal
cd /d "%~dp0"

set PORT=8093

REM Free the port if a previous run is still holding it.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:"LISTENING .*:%PORT% " 2^>nul') do (
  taskkill /f /pid %%P >nul 2>&1
)

where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher "py" not found. Install Python 3 first.
  pause
  exit /b 1
)

echo Serving %CD% at http://localhost:%PORT%/
echo.
echo   Drafts   http://localhost:%PORT%/_drafts/
echo   Articles http://localhost:%PORT%/articles/
echo.
echo Close this window to stop the server.

start "" "http://localhost:%PORT%/_drafts/"
py -3 -m http.server %PORT%
