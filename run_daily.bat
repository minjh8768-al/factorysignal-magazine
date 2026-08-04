@echo off
REM Daily job for Task Scheduler. ASCII only - see project CLAUDE.md.
REM
REM Generates one draft per category, runs the checks, publishes the ones that pass
REM the sanity gate (with English versions), and pushes.
REM Articles that fail the gate stay in _drafts\ for a human to look at.
REM
REM The gate only catches structural failures: too short, LLM boilerplate, repeated
REM sentences, impossible numbers. It cannot catch a wrong name or a wrong incumbent.
REM Read _drafts\_daily.log each morning.
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher "py" not found.
  exit /b 1
)

py -3 "tools\daily.py" --publish %*
set RC=%errorlevel%

REM Push only when something actually changed.
git diff --quiet --exit-code HEAD -- articles
if errorlevel 1 (
  git add -A articles
  git commit -q -m "chore(daily): automated batch %DATE%"
  git push -q origin main
  git push -q origin main:master
  echo Pushed.
) else (
  echo Nothing to push.
)

exit /b %RC%
