@echo off
title Uninstall Jarvis Autostart
cd /d "%~dp0"

echo Removing Jarvis from Windows Startup...
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.lnk" >nul 2>&1

echo [*] Stopping active background assistant...
call "%~dp0stop_jarvis.bat"

echo [+] Jarvis autostart removed and background process stopped.
timeout /t 2 >nul
