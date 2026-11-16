@echo off
title Jarvis Personal AI Assistant
cd /d "%~dp0"
cls
echo ========================================================
echo       Jarvis Hands-Free Desktop Voice Assistant 🎙️
echo ========================================================
echo.
echo Assistant: Jarvis
echo Wake Word : Say "Jarvis" or "Hey Jarvis"
echo.

set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

"%PY_EXE%" -u main.py --voice
echo.
echo ========================================================
echo  Jarvis stopped. Press any key to exit or restart.
echo ========================================================
pause
