import os
import sys
import subprocess
import threading

def _send_toast(title: str, message: str):
    """Spawns a hidden PowerShell process to display a Windows balloon notification."""
    try:
        clean_title = title.replace("'", "").replace('"', "").strip()
        clean_msg = message.replace("'", "").replace('"', "").strip()
        if len(clean_msg) > 200:
            clean_msg = clean_msg[:197] + "..."

        ps_script = f"""
[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.BalloonTipTitle = '{clean_title}'
$notify.BalloonTipText = '{clean_msg}'
$notify.Visible = $True
$notify.ShowBalloonTip(4000)
Start-Sleep -Milliseconds 800
$notify.Dispose()
"""
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            creationflags=creation_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

def notify_user(title: str, message: str):
    """Non-blocking notification trigger."""
    threading.Thread(target=_send_toast, args=(title, message), daemon=True).start()

if __name__ == "__main__":
    notify_user("Jarvis Online", "Listening for 'Jarvis' or 'Hey Jarvis'")
