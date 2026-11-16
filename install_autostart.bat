@echo off
title Install Jarvis Always-On Autostart
cd /d "%~dp0"

echo ========================================================
echo       Configuring Jarvis Always-On Background Mode
echo ========================================================
echo.
echo Setting up Jarvis to run automatically on Windows startup...

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([IO.Path]::Combine($env:APPDATA, 'Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.lnk')); $sc.TargetPath = 'wscript.exe'; $sc.Arguments = '\"' + (Get-Location).Path + '\start_jarvis_silently.vbs\"'; $sc.WorkingDirectory = (Get-Location).Path; $sc.WindowStyle = 7; $sc.Description = 'Jarvis Hands-Free AI Voice Assistant'; $sc.Save()"

if %ERRORLEVEL% EQU 0 (
    echo [+] Success! Jarvis will now launch silently in the background on startup.
    echo [*] Starting Jarvis right now in the background...
    wscript.exe "%~dp0start_jarvis_silently.vbs"
    echo [+] Jarvis is NOW ACTIVE and listening for "Jarvis"!
) else (
    echo [!] Failed to create startup shortcut.
)

echo.
pause
