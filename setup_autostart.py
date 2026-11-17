import os
import sys
import subprocess
from pathlib import Path

def setup_autostart():
    project_dir = Path(__file__).resolve().parent
    vbs_path = project_dir / "start_jarvis_silently.vbs"
    startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    shortcut_path = startup_dir / "Jarvis.lnk"

    ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{shortcut_path}')
$sc.TargetPath = 'wscript.exe'
$sc.Arguments = '"{vbs_path}"'
$sc.WorkingDirectory = '{project_dir}'
$sc.WindowStyle = 7
$sc.Description = 'Jarvis Unified AI Assistant (Voice, Telegram & Scheduler)'
$sc.Save()
"""
    ps_file = project_dir / "temp_audio" / "create_shortcut.ps1"
    ps_file.parent.mkdir(exist_ok=True)
    ps_file.write_text(ps_script, encoding="utf-8")

    result = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_file)], capture_output=True, text=True)
    ps_file.unlink(missing_ok=True)

    if result.returncode == 0:
        print("[+] Windows Startup shortcut created successfully:")
        print(f"    {shortcut_path}")
        return True
    else:
        print(f"[-] Failed to create shortcut: {result.stderr}")
        return False

if __name__ == "__main__":
    setup_autostart()
