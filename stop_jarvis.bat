@echo off
title Stop Jarvis Assistant
cd /d "%~dp0"

echo [*] Stopping background Jarvis Assistant...

if exist "temp_audio\jarvis.pid" (
    set /p JARVIS_PID=<"temp_audio\jarvis.pid"
    if defined JARVIS_PID (
        taskkill /f /pid %JARVIS_PID% >nul 2>&1
        del "temp_audio\jarvis.pid" >nul 2>&1
    )
)

:: Failsafe: terminate pythonw if it was running voice assistant
taskkill /f /im pythonw.exe >nul 2>&1

echo [+] Jarvis Assistant stopped.
timeout /t 2 >nul
