@echo off
REM Deploy to Vercel production using a token file. ASCII only - see project CLAUDE.md.
REM
REM Why a token instead of "vercel login": this PC's hostname is not ASCII, and the
REM Vercel CLI login flow puts the hostname in an HTTP header, which throws
REM "Cannot convert argument to a ByteString". Token auth skips that flow entirely.
REM
REM Setup once: create a token at https://vercel.com/account/tokens
REM             paste it (token only, no quotes) into .vercel-token in this folder.
setlocal
cd /d "%~dp0"

if not exist ".vercel-token" (
  echo Missing .vercel-token
  echo   1. Open https://vercel.com/account/tokens and create a token
  echo   2. Save it as .vercel-token in this folder ^(token text only^)
  pause
  exit /b 1
)

set /p VTOKEN=<.vercel-token
if "%VTOKEN%"=="" (
  echo .vercel-token is empty.
  pause
  exit /b 1
)

if not exist ".vercel\project.json" (
  echo Linking this folder to the Vercel project...
  call npx --yes vercel@latest link --yes --token %VTOKEN%
  if errorlevel 1 (
    echo Link failed.
    pause
    exit /b 1
  )
)

echo Deploying to production...
call npx --yes vercel@latest deploy --prod --yes --token %VTOKEN%
if errorlevel 1 (
  echo Deploy failed.
  pause
  exit /b 1
)

echo Done.
pause
