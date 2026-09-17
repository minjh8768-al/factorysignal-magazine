@echo off
REM Daily market analysis article. ASCII only - see project CLAUDE.md.
REM
REM agenda.py decides today's topic and format:
REM   Mon-Fri  one of five market themes, rotating
REM   Sat      crypto only - equity markets are closed
REM   Sun      weekly review across markets
REM
REM The compliance gate refuses to write a draft that reads as investment advice.
REM If it blocks, nothing is published and the run exits without a file.
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher "py" not found.
  exit /b 1
)

py -3 "tools\analysis.py" %*
set RC=%errorlevel%
if not "%RC%"=="0" (
  echo Analysis did not produce a draft. Nothing published.
  exit /b %RC%
)

REM Publish only when a draft was actually written.
py -3 "tools\publish.py" --apply
if errorlevel 1 exit /b 1

git diff --quiet --exit-code HEAD -- articles
if errorlevel 1 (
  git add -A articles
  git commit -q -m "chore(analysis): market analysis %DATE%"
  git push -q origin main
  git push -q origin main:master
  echo Pushed.
  REM Telegram sends only the categories in telegram_categories.
  py -3 "tools\telegram.py" --send
) else (
  echo Nothing to push.
)

exit /b 0
