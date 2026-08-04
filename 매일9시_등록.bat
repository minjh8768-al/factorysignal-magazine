@echo off
REM Register/unregister the 9 AM daily draft job in Windows Task Scheduler.
REM ASCII only - see project CLAUDE.md.
setlocal
cd /d "%~dp0"

set TASK=FactoryMagazineDaily

if /i "%1"=="off" goto remove
if /i "%1"=="status" goto status
if /i "%1"=="run" goto runnow

echo Registering "%TASK%" to run every day at 09:00
echo   script: %~dp0run_daily.bat
echo.
echo This job creates drafts and runs the fact-check.
echo It does NOT publish - you review in the morning and publish yourself.
echo.
schtasks /Create /TN "%TASK%" /TR "\"%~dp0run_daily.bat\"" /SC DAILY /ST 09:00 /F /RL LIMITED
if errorlevel 1 (
  echo.
  echo Registration failed. Try running this file as Administrator.
  pause
  exit /b 1
)
echo.
echo Done. The PC must be on and signed in at 09:00.
echo.
echo   status : matil9si_deungrok.bat status
echo   run now: matil9si_deungrok.bat run
echo   remove : matil9si_deungrok.bat off
pause
exit /b 0

:status
schtasks /Query /TN "%TASK%" /V /FO LIST 2>nul | findstr /i "TaskName Status Next Last Result"
if errorlevel 1 echo Task "%TASK%" is not registered.
pause
exit /b 0

:runnow
echo Running now...
schtasks /Run /TN "%TASK%"
pause
exit /b 0

:remove
schtasks /Delete /TN "%TASK%" /F
echo Removed.
pause
exit /b 0
