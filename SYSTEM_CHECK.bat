@echo off
echo ===== SYSTEM CHECK =====
echo.
echo Windows:
ver
echo.
echo PowerShell:
powershell -NoProfile -Command "$PSVersionTable.PSVersion.ToString()"
echo.
echo Git:
where git
git --version
echo.
echo GitHub CLI:
where gh
gh --version
echo.
echo GitHub auth:
gh auth status
echo.
pause
