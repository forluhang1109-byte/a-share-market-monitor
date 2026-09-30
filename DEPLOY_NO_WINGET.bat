@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo A-Share Market Monitor - GitHub Deploy v0.4
echo No winget required
echo ==========================================
echo.

set "PS=powershell.exe -NoProfile -ExecutionPolicy Bypass"

REM ---------- Ensure Git ----------
where git >nul 2>nul
if errorlevel 1 (
  echo [1/4] Git not found. Downloading latest Git for Windows...
  %PS% -Command ^
    "$ErrorActionPreference='Stop';" ^
    "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;" ^
    "$r=Invoke-RestMethod 'https://api.github.com/repos/git-for-windows/git/releases/latest';" ^
    "$a=$r.assets | Where-Object { $_.name -match '^Git-.*-64-bit\.exe$' } | Select-Object -First 1;" ^
    "if(-not $a){throw 'Git 64-bit installer asset not found'};" ^
    "$out=Join-Path $env:TEMP 'git-installer.exe';" ^
    "Invoke-WebRequest $a.browser_download_url -OutFile $out -UseBasicParsing;" ^
    "Start-Process $out -ArgumentList '/VERYSILENT','/NORESTART','/NOCANCEL','/SP-' -Wait"
  if errorlevel 1 goto :error

  set "PATH=C:\Program Files\Git\cmd;C:\Program Files\Git\bin;%PATH%"
)

where git >nul 2>nul
if errorlevel 1 (
  echo Git installation completed but git.exe is not visible yet.
  echo Close this window and run DEPLOY_NO_WINGET.bat again.
  pause
  exit /b 0
)

echo [1/4] Git OK:
git --version
echo.

REM ---------- Ensure GitHub CLI ----------
where gh >nul 2>nul
if errorlevel 1 (
  echo [2/4] GitHub CLI not found. Downloading latest official MSI...
  %PS% -Command ^
    "$ErrorActionPreference='Stop';" ^
    "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;" ^
    "$r=Invoke-RestMethod 'https://api.github.com/repos/cli/cli/releases/latest';" ^
    "$a=$r.assets | Where-Object { $_.name -match '^gh_.*_windows_amd64\.msi$' } | Select-Object -First 1;" ^
    "if(-not $a){throw 'GitHub CLI windows amd64 MSI not found'};" ^
    "$out=Join-Path $env:TEMP 'gh-installer.msi';" ^
    "Invoke-WebRequest $a.browser_download_url -OutFile $out -UseBasicParsing;" ^
    "Start-Process 'msiexec.exe' -ArgumentList '/i',('\"'+$out+'\"'),'/qn','/norestart' -Wait"
  if errorlevel 1 goto :error

  set "PATH=C:\Program Files\GitHub CLI;%PATH%"
)

where gh >nul 2>nul
if errorlevel 1 (
  echo GitHub CLI installation completed but gh.exe is not visible yet.
  echo Close this window and run DEPLOY_NO_WINGET.bat again.
  pause
  exit /b 0
)

echo [2/4] GitHub CLI OK:
gh --version
echo.

REM ---------- GitHub auth ----------
echo [3/4] Checking GitHub login...
gh auth status >nul 2>nul
if errorlevel 1 (
  echo.
  echo GitHub authorization is required once.
  echo Your browser will open. Complete the GitHub authorization there.
  echo.
  gh auth login --hostname github.com --git-protocol https --web
  if errorlevel 1 goto :error
)

echo GitHub login OK.
echo.

REM ---------- Initialize and push ----------
echo [4/4] Preparing repository...

if not exist ".git" (
  git init
  if errorlevel 1 goto :error
)

git config user.name "a-share-monitor"
git config user.email "a-share-monitor@users.noreply.github.com"

git add .
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "init: a-share market monitor"
  if errorlevel 1 goto :error
)

git branch -M main

git remote get-url origin >nul 2>nul
if not errorlevel 1 (
  echo Existing remote found:
  git remote get-url origin
  echo Pushing...
  git push -u origin main
  if errorlevel 1 goto :error
  goto :success
)

echo.
set /p REPO_NAME=Repository name [a-share-market-monitor]:
if "%REPO_NAME%"=="" set "REPO_NAME=a-share-market-monitor"

echo.
echo Creating PUBLIC repository: %REPO_NAME%
gh repo create "%REPO_NAME%" --public --source . --remote origin --push
if errorlevel 1 goto :error

:success
echo.
echo ==========================================
echo DEPLOY SUCCESS
echo ==========================================
echo Repository URL:
gh repo view --json url -q .url
echo.
echo Send this URL to ChatGPT.
echo.
pause
exit /b 0

:error
echo.
echo ==========================================
echo DEPLOY FAILED
echo ==========================================
echo Please send ChatGPT a screenshot of the last 10-20 lines above.
echo.
pause
exit /b 1
