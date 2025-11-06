@echo off
:: ----------------------------
:: 5EMA AutoTrader Backup Script
:: ----------------------------
:: Automatically adds, commits, and pushes all code changes to GitHub.

set REPO_DIR=D:\Work\AI\5EMA_AutoTrader\5EMA_AutoTrader
set COMMIT_MSG=%1

if "%COMMIT_MSG%"=="" set COMMIT_MSG=Auto backup commit

echo.
echo 🚀 Backing up project to GitHub...
cd /d "%REPO_DIR%"

echo.
echo 🧹 Checking repository status...
git status

echo.
echo 🗃️  Adding all files...
git add .

echo.
echo 💾 Committing changes...
git commit -m "%COMMIT_MSG%"

echo.
echo ☁️  Pushing to GitHub main branch...
git push origin main

echo.
echo ✅ Backup complete!
echo.
pause
