@echo off
title Jarvis AI Assistant
cd /d "%~dp0"
cls
echo ========================================================
echo       Jarvis Hands-Free Desktop Voice Assistant
echo ========================================================
echo.
echo Wake-word engine is active.
echo Say "Jarvis" or "Hey Jarvis" to begin speaking.
echo.
python -u main.py --voice
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] An error occurred while running Jarvis.
    pause
)
