@echo off
title Jarvis Personal AI Assistant (Unified Voice + Telegram + Scheduler)
cd /d "%~dp0"
cls
echo ========================================================
echo       Jarvis Unified Assistant (Voice + Telegram) 🎙️📱
echo ========================================================
echo.
echo Assistant : Jarvis
echo Wake Word : Say "Jarvis" or "Hey Jarvis"
echo Telegram  : Companion bot + Autonomous Scheduler active
echo.

set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

"%PY_EXE%" -u main.py --all
echo.
echo ========================================================
echo  Jarvis stopped. Press any key to exit or restart.
echo ========================================================
pause
