@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo A-Share Market Monitor - GitHub Deploy
echo ==========================================
echo.

where winget >nul 2>nul
if errorlevel 1 (
  echo ERROR: winget was not found.
  echo Please install "App Installer" from Microsoft Store, then run this file again.
  pause
  exit /b 1
)

set NEED_RESTART=0

where git >nul 2>nul
if errorlevel 1 (
  echo Git was not found. Installing Git...
  winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo ERROR: Git installation failed.
    pause
    exit /b 1
  )
  set NEED_RESTART=1
)

where gh >nul 2>nul
if errorlevel 1 (
  echo GitHub CLI was not found. Installing GitHub CLI...
  winget install --id GitHub.cli -e --source winget --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo ERROR: GitHub CLI installation failed.
    pause
    exit /b 1
  )
  set NEED_RESTART=1
)

if "%NEED_RESTART%"=="1" (
  echo.
  echo Git and/or GitHub CLI was installed successfully.
  echo CLOSE this window, then double-click this BAT file again.
  pause
  exit /b 0
)

echo Checking GitHub login...
gh auth status >nul 2>nul
if errorlevel 1 (
  echo.
  echo A browser window will open for GitHub authorization.
  echo Complete the authorization once, then return here.
  gh auth login --web
  if errorlevel 1 goto :error
)

if not exist ".git" (
  echo Initializing Git repository...
  git init
  if errorlevel 1 goto :error
)

git config user.name "a-share-monitor"
git config user.email "a-share-monitor@users.noreply.github.com"

git add .
git commit -m "init: a-share market monitor" >nul 2>nul

git remote get-url origin >nul 2>nul
if not errorlevel 1 (
  echo Existing GitHub remote found:
  git remote get-url origin
  echo.
  echo Pushing project...
  git branch -M main
  git push -u origin main
  if errorlevel 1 goto :error
  goto :success
)

echo.
set /p REPO_NAME=Enter repository name [a-share-market-monitor]:
if "%REPO_NAME%"=="" set REPO_NAME=a-share-market-monitor

echo.
echo Creating PUBLIC GitHub repository: %REPO_NAME%
echo Public mode lets ChatGPT read the generated JSON directly.
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
echo Copy the URL above and send it to ChatGPT.
pause
exit /b 0

:error
echo.
echo ==========================================
echo DEPLOY FAILED
echo ==========================================
echo Take a screenshot of the last error lines and send it to ChatGPT.
pause
exit /b 1
