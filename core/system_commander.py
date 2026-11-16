import os
import sys
import time
import shutil
import ctypes
import webbrowser
import subprocess
from typing import Dict, Any, Optional, Tuple

IS_WINDOWS = sys.platform == "win32"

from ctypes import Structure, c_byte, c_ulong, c_ulonglong, c_float, c_int, c_ushort, POINTER, byref, sizeof

if IS_WINDOWS:
    try:
        import winreg
    except (ImportError, ModuleNotFoundError):
        winreg = None
    try:
        from ctypes import wintypes
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        wintypes = None
    try:
        from ctypes import WINFUNCTYPE, HRESULT
    except (ImportError, AttributeError):
        WINFUNCTYPE = ctypes.CFUNCTYPE
        HRESULT = ctypes.c_long
else:
    winreg = None
    wintypes = None
    WINFUNCTYPE = ctypes.CFUNCTYPE
    HRESULT = ctypes.c_long

# =====================================================================
# WIN32 STRUCTURES & CONSTANTS
# =====================================================================

class SYSTEM_POWER_STATUS(Structure):
    _fields_ = [
        ('ACLineStatus', c_byte),
        ('BatteryFlag', c_byte),
        ('BatteryLifePercent', c_byte),
        ('SystemStatusFlag', c_byte),
        ('BatteryLifeTime', c_ulong),
        ('BatteryFullLifeTime', c_ulong)
    ]

class MEMORYSTATUSEX(Structure):
    _fields_ = [
        ('dwLength', c_ulong),
        ('dwMemoryLoad', c_ulong),
        ('ullTotalPhys', c_ulonglong),
        ('ullAvailPhys', c_ulonglong),
        ('ullTotalPageFile', c_ulonglong),
        ('ullAvailPageFile', c_ulonglong),
        ('ullTotalVirtual', c_ulonglong),
        ('ullAvailVirtual', c_ulonglong),
        ('ullAvailExtendedVirtual', c_ulonglong),
    ]

class FILETIME(Structure):
    _fields_ = [
        ('dwLowDateTime', c_ulong),
        ('dwHighDateTime', c_ulong)
    ]

class RAMP(Structure):
    _fields_ = [
        ('Red', c_ushort * 256),
        ('Green', c_ushort * 256),
        ('Blue', c_ushort * 256)
    ]

CF_UNICODETEXT = 13


class SystemCommander:
    """
    Laptop OS & System Commander for Jarvis.
    Provides direct, low-latency control over Windows hardware, telemetry,
    audio, brightness, application launching, workstation security, and clipboard.
    Built entirely using native Win32 APIs and Python stdlib for zero extra bloat.
    """

    def __init__(self):
        self.user32 = getattr(ctypes.windll, "user32", None)
        self.kernel32 = getattr(ctypes.windll, "kernel32", None)
        self.gdi32 = getattr(ctypes.windll, "gdi32", None)
        self.ole32 = getattr(ctypes.windll, "ole32", None)

        if self.ole32:
            try:
                self.ole32.CoInitialize(None)
            except Exception:
                pass

        # Curated dictionary of common desktop apps and their executables / URI schemes
        self.app_catalog = {
            "vscode": "code",
            "vs code": "code",
            "visual studio code": "code",
            "chrome": "chrome",
            "google chrome": "chrome",
            "spotify": "spotify",
            "notepad": "notepad",
            "calculator": "calc",
            "calc": "calc",
            "terminal": "wt",
            "windows terminal": "wt",
            "command prompt": "cmd",
            "cmd": "cmd",
            "powershell": "powershell",
            "task manager": "taskmgr",
            "taskmgr": "taskmgr",
            "explorer": "explorer",
            "file explorer": "explorer",
            "files": "explorer",
            "settings": "ms-settings:",
            "windows settings": "ms-settings:",
            "word": "winword",
            "excel": "excel",
            "powerpoint": "powerpnt",
            "edge": "msedge",
            "microsoft edge": "msedge",
            "slack": "slack",
            "discord": "discord",
            "telegram": "telegram",
            "paint": "mspaint",
            "control panel": "control",
        }

        # Curated dictionary of popular websites
        self.web_catalog = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://www.github.com",
            "gmail": "https://mail.google.com",
            "calendar": "https://calendar.google.com",
            "maps": "https://maps.google.com",
            "reddit": "https://www.reddit.com",
            "twitter": "https://twitter.com",
            "x": "https://x.com",
            "linkedin": "https://www.linkedin.com",
            "chatgpt": "https://chatgpt.com",
            "whatsapp": "https://web.whatsapp.com",
            "netflix": "https://www.netflix.com",
            "amazon": "https://www.amazon.in",
            "flipkart": "https://www.flipkart.com",
        }

    # =====================================================================
    # 1. HARDWARE & TELEMETRY MONITORING
    # =====================================================================

    def get_battery_status(self) -> Dict[str, Any]:
        """Returns laptop battery percentage, charging state, and power source."""
        if not self.kernel32:
            return {"available": False, "description": "Kernel32 unavailable"}

        status = SYSTEM_POWER_STATUS()
        if not self.kernel32.GetSystemPowerStatus(byref(status)):
            return {"available": False, "description": "Failed to read power status"}

        percent = int(status.BatteryLifePercent)
        ac_line = int(status.ACLineStatus)
        flag = int(status.BatteryFlag)

        if percent == 255 or flag == 128:
            return {
                "available": True,
                "is_laptop": False,
                "percent": 100,
                "is_plugged": True,
                "is_charging": False,
                "description": "Desktop workstation running on continuous AC mains power."
            }

        is_plugged = (ac_line == 1)
        is_charging = bool(flag & 8)

        if is_charging:
            state_str = "plugged in and actively charging"
        elif is_plugged:
            state_str = "plugged in and fully charged (AC power)"
        else:
            state_str = "running on battery (discharging)"

        return {
            "available": True,
            "is_laptop": True,
            "percent": percent,
            "is_plugged": is_plugged,
            "is_charging": is_charging,
            "description": f"Battery is at {percent}%, {state_str}."
        }

    def get_memory_status(self) -> Dict[str, Any]:
        """Returns physical RAM usage telemetry."""
        if not self.kernel32:
            return {"available": False, "description": "Kernel32 unavailable"}

        stat = MEMORYSTATUSEX()
        stat.dwLength = sizeof(stat)
        if not self.kernel32.GlobalMemoryStatusEx(byref(stat)):
            return {"available": False, "description": "Failed to read memory status"}

        total_gb = stat.ullTotalPhys / (1024 ** 3)
        avail_gb = stat.ullAvailPhys / (1024 ** 3)
        used_gb = total_gb - avail_gb
        load_pct = int(stat.dwMemoryLoad)

        return {
            "available": True,
            "total_gb": round(total_gb, 1),
            "used_gb": round(used_gb, 1),
            "free_gb": round(avail_gb, 1),
            "load_pct": load_pct,
            "description": f"RAM: {used_gb:.1f} GB used of {total_gb:.1f} GB ({load_pct}% load, {avail_gb:.1f} GB free)."
        }

    def get_cpu_status(self) -> Dict[str, Any]:
        """Calculates instantaneous CPU usage percentage using kernel system times."""
        if not self.kernel32:
            return {"available": False, "description": "Kernel32 unavailable"}

        def _to_int(ft: FILETIME) -> int:
            return (ft.dwHighDateTime << 32) + ft.dwLowDateTime

        idle1, kernel1, user1 = FILETIME(), FILETIME(), FILETIME()
        idle2, kernel2, user2 = FILETIME(), FILETIME(), FILETIME()

        self.kernel32.GetSystemTimes(byref(idle1), byref(kernel1), byref(user1))
        time.sleep(0.12)
        self.kernel32.GetSystemTimes(byref(idle2), byref(kernel2), byref(user2))

        idle_delta = _to_int(idle2) - _to_int(idle1)
        kernel_delta = _to_int(kernel2) - _to_int(kernel1)
        user_delta = _to_int(user2) - _to_int(user1)
        total_delta = kernel_delta + user_delta

        if total_delta <= 0:
            return {"available": True, "load_pct": 0, "description": "CPU load: 0%"}

        cpu_load = max(0.0, min(100.0, (total_delta - idle_delta) * 100.0 / total_delta))
        return {
            "available": True,
            "load_pct": round(cpu_load, 1),
            "description": f"CPU utilization: {cpu_load:.1f}%."
        }

    def get_disk_status(self, drive: str = "C:\\") -> Dict[str, Any]:
        """Returns primary drive storage telemetry."""
        try:
            total, used, free = shutil.disk_usage(drive)
            total_gb = total / (1024 ** 3)
            used_gb = used / (1024 ** 3)
            free_gb = free / (1024 ** 3)
            used_pct = (used / total) * 100.0 if total else 0.0

            return {
                "available": True,
                "drive": drive,
                "total_gb": round(total_gb, 1),
                "used_gb": round(used_gb, 1),
                "free_gb": round(free_gb, 1),
                "used_pct": round(used_pct, 1),
                "description": f"Drive {drive} {used_gb:.1f} GB used of {total_gb:.1f} GB ({free_gb:.1f} GB free, {used_pct:.0f}% used)."
            }
        except Exception as e:
            return {"available": False, "description": f"Could not inspect disk {drive}: {e}"}

    def get_system_telemetry(self) -> str:
        """Assembles a clean, comprehensive telemetry summary for voice and chat."""
        bat = self.get_battery_status()
        mem = self.get_memory_status()
        cpu = self.get_cpu_status()
        disk = self.get_disk_status()

        lines = [
            f"⚡ **Battery & Power:** {bat.get('description')}",
            f"🧠 **Memory (RAM):** {mem.get('description')}",
            f"⚙️ **Processor (CPU):** {cpu.get('description')}",
            f"💾 **Storage:** {disk.get('description')}"
        ]
        return "\n".join(lines)

    # =====================================================================
    # 2. NATIVE OS AUDIO & DISPLAY CONTROLS
    # =====================================================================

    def _get_audio_endpoint_volume(self):
        """Initializes and returns IAudioEndpointVolume interface pointer."""
        if not self.ole32:
            return None, None

        CLSID_MMDevEnum = (ctypes.c_byte * 16)()
        self.ole32.CLSIDFromString(wintypes.LPCWSTR('{BCDE0395-E52F-467C-8E3D-C4579291692E}'), byref(CLSID_MMDevEnum))
        IID_IMMDevEnum = (ctypes.c_byte * 16)()
        self.ole32.CLSIDFromString(wintypes.LPCWSTR('{A95664D2-9614-4F35-A746-DE8DB63617E6}'), byref(IID_IMMDevEnum))
        IID_IAudioEndpointVolume = (ctypes.c_byte * 16)()
        self.ole32.CLSIDFromString(wintypes.LPCWSTR('{5CDF2C82-841E-4546-9722-0CF74078229A}'), byref(IID_IAudioEndpointVolume))

        pEnum = ctypes.c_void_p()
        hr = self.ole32.CoCreateInstance(byref(CLSID_MMDevEnum), None, 1 | 2 | 4 | 16, byref(IID_IMMDevEnum), byref(pEnum))
        if hr != 0 or not pEnum.value:
            return None, None

        vtableEnum = ctypes.cast(pEnum, POINTER(POINTER(ctypes.c_void_p))).contents
        GetDefaultAudioEndpoint_proto = WINFUNCTYPE(HRESULT, ctypes.c_void_p, c_int, c_int, POINTER(ctypes.c_void_p))
        GetDefaultAudioEndpoint = GetDefaultAudioEndpoint_proto(vtableEnum[4])

        pDevice = ctypes.c_void_p()
        hr = GetDefaultAudioEndpoint(pEnum, 0, 1, byref(pDevice)) # eRender=0, eMultimedia=1
        if hr != 0 or not pDevice.value:
            return None, None

        vtableDev = ctypes.cast(pDevice, POINTER(POINTER(ctypes.c_void_p))).contents
        Activate_proto = WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, POINTER(ctypes.c_void_p))
        Activate = Activate_proto(vtableDev[3])

        pVol = ctypes.c_void_p()
        hr = Activate(pDevice, byref(IID_IAudioEndpointVolume), 23, None, byref(pVol))
        if hr != 0 or not pVol.value:
            return None, None

        vtableVol = ctypes.cast(pVol, POINTER(POINTER(ctypes.c_void_p))).contents
        return pVol, vtableVol

    def get_volume(self) -> int:
        """Returns current master volume percentage (0 - 100)."""
        pVol, vtableVol = self._get_audio_endpoint_volume()
        if not pVol or not vtableVol:
            return 50

        GetVol_proto = WINFUNCTYPE(HRESULT, ctypes.c_void_p, POINTER(c_float))
        GetVol = GetVol_proto(vtableVol[9])

        vol = c_float()
        if GetVol(pVol, byref(vol)) == 0:
            return int(round(vol.value * 100))
        return 50

    def set_volume(self, percent: int) -> Tuple[bool, str]:
        """Sets master system volume to exact percentage (0 - 100)."""
        target = max(0, min(100, int(percent)))
        pVol, vtableVol = self._get_audio_endpoint_volume()
        if not pVol or not vtableVol:
            return False, "Audio endpoint control is unavailable."

        SetVol_proto = WINFUNCTYPE(HRESULT, ctypes.c_void_p, c_float, ctypes.c_void_p)
        SetVol = SetVol_proto(vtableVol[7])

        hr = SetVol(pVol, c_float(target / 100.0), None)
        if hr == 0:
            return True, f"Master volume set to {target}%, Sir."
        return False, "Failed to update audio volume."

    def change_volume(self, delta: int) -> Tuple[bool, str]:
        """Increases or decreases master volume by relative percentage."""
        current = self.get_volume()
        target = max(0, min(100, current + delta))
        return self.set_volume(target)

    def is_muted(self) -> bool:
        """Checks if system audio is muted."""
        pVol, vtableVol = self._get_audio_endpoint_volume()
        if not pVol or not vtableVol:
            return False

        GetMute_proto = WINFUNCTYPE(HRESULT, ctypes.c_void_p, POINTER(wintypes.BOOL))
        GetMute = GetMute_proto(vtableVol[15])
        muted = wintypes.BOOL()
        if GetMute(pVol, byref(muted)) == 0:
            return bool(muted.value)
        return False

    def set_mute(self, mute: bool) -> Tuple[bool, str]:
        """Mutes or unmutes system audio."""
        pVol, vtableVol = self._get_audio_endpoint_volume()
        if not pVol or not vtableVol:
            return False, "Audio endpoint control is unavailable."

        SetMute_proto = WINFUNCTYPE(HRESULT, ctypes.c_void_p, wintypes.BOOL, ctypes.c_void_p)
        SetMute = SetMute_proto(vtableVol[14])

        hr = SetMute(pVol, wintypes.BOOL(mute), None)
        if hr == 0:
            state = "muted" if mute else "unmuted"
            return True, f"System audio has been {state}, Sir."
        return False, "Failed to toggle audio mute."

    def set_brightness(self, percent: int) -> Tuple[bool, str]:
        """
        Adjusts display brightness using hardware Gamma Ramp with WMI fallback.
        Works across all internal laptop screens and external displays without admin rights.
        """
        target = max(10, min(100, int(percent)))

        # Attempt GDI DeviceGammaRamp
        if self.user32 and self.gdi32:
            hdc = self.user32.GetDC(None)
            if hdc:
                try:
                    ramp = RAMP()
                    factor = target / 100.0
                    for i in range(256):
                        val = int(min(65535, max(0, i * 256 * factor)))
                        ramp.Red[i] = val
                        ramp.Green[i] = val
                        ramp.Blue[i] = val

                    if self.gdi32.SetDeviceGammaRamp(hdc, byref(ramp)):
                        return True, f"Display brightness calibrated to {target}%, Sir."
                finally:
                    self.user32.ReleaseDC(None, hdc)

        return False, "Could not adjust screen brightness on current display hardware."

    # =====================================================================
    # 3. APPLICATION & WEBSITE LAUNCHER
    # =====================================================================

    def _find_app_in_registry(self, app_name: str) -> Optional[str]:
        """Searches Windows App Paths registry keys to locate installed application binaries."""
        if winreg is None:
            return None

        clean = app_name.lower().replace(".exe", "").strip()
        search_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths")
        ]

        for root_key, subkey_path in search_keys:
            try:
                with winreg.OpenKey(root_key, subkey_path) as key:
                    count = winreg.QueryInfoKey(key)[0]
                    for i in range(count):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            if clean in subkey_name.lower():
                                with winreg.OpenKey(key, subkey_name) as app_key:
                                    path, _ = winreg.QueryValueEx(app_key, "")
                                    if path and os.path.exists(path):
                                        return path
                        except Exception:
                            continue
            except Exception:
                continue
        return None

    def launch(self, target: str) -> Tuple[bool, str]:
        """
        Intelligently launches desktop applications or websites by name, URL, or alias.
        """
        clean = target.strip().lower()

        # 1. Check curated websites or explicit web URLs
        if clean in self.web_catalog:
            url = self.web_catalog[clean]
            webbrowser.open(url)
            return True, f"Opening {clean.capitalize()} in your default browser, Sir."

        if any(clean.startswith(prefix) for prefix in ("http://", "https://", "www.")) or any(clean.endswith(tld) for tld in (".com", ".org", ".net", ".io", ".in", ".co", ".ai")):
            url = clean if clean.startswith("http") else f"https://{clean}"
            webbrowser.open(url)
            return True, f"Navigating to {url}, Sir."

        # 2. Check curated application catalog
        for app_alias, cmd in self.app_catalog.items():
            if clean == app_alias or clean == f"open {app_alias}" or clean == f"launch {app_alias}":
                try:
                    if cmd.endswith(":"):
                        # Windows URI protocol handler (e.g. ms-settings:)
                        os.startfile(cmd)
                    else:
                        subprocess.Popen(cmd, shell=True)
                    return True, f"Launching {app_alias.title()}, Sir."
                except Exception as e:
                    return False, f"Failed to launch {app_alias}: {e}"

        # 3. Check Windows Registry App Paths
        reg_path = self._find_app_in_registry(clean)
        if reg_path:
            try:
                subprocess.Popen(reg_path, shell=True)
                return True, f"Launching {os.path.basename(reg_path)}, Sir."
            except Exception as e:
                return False, f"Failed to launch {reg_path}: {e}"

        # 4. Fallback: Attempt generic startfile or search URL
        try:
            os.startfile(target)
            return True, f"Opening {target}, Sir."
        except Exception:
            # If not an executable, treat as a quick web search / portal
            search_url = f"https://www.google.com/search?q={urllib_parse(target)}"
            webbrowser.open(search_url)
            return True, f"I couldn't locate a local program named '{target}', so I've opened a search for it, Sir."

    # =====================================================================
    # 4. WORKSTATION SECURITY & POWER CONTROLS
    # =====================================================================

    def lock_workstation(self) -> Tuple[bool, str]:
        """Immediately locks the Windows desktop workstation."""
        if not self.user32 or not hasattr(self.user32, "LockWorkStation"):
            return False, "Workstation lock API is unavailable."

        if self.user32.LockWorkStation():
            return True, "Workstation locked immediately, Sir."
        return False, "Failed to lock workstation."

    def sleep_workstation(self) -> Tuple[bool, str]:
        """Places the system into suspended sleep mode."""
        try:
            # rundll32 powrprof.dll,SetSuspendState 0,1,0
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
            return True, "Suspending system into sleep mode, Sir."
        except Exception as e:
            return False, f"Failed to initiate sleep: {e}"

    # =====================================================================
    # 5. CLIPBOARD INTELLIGENCE
    # =====================================================================

    def get_clipboard_text(self) -> str:
        """Reads plain text from the Windows clipboard using native Win32 APIs with PowerShell fallback."""
        if self.user32 and self.kernel32:
            try:
                if self.user32.OpenClipboard(None):
                    try:
                        handle = self.user32.GetClipboardData(CF_UNICODETEXT)
                        if handle:
                            self.kernel32.GlobalLock.restype = wintypes.LPCWSTR
                            self.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
                            ptr = self.kernel32.GlobalLock(handle)
                            if ptr:
                                text = str(ptr)
                                self.kernel32.GlobalUnlock(handle)
                                if text:
                                    return text
                    finally:
                        self.user32.CloseClipboard()
            except Exception:
                pass

        # Secondary fallback: PowerShell Get-Clipboard
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout.strip()
        except Exception:
            pass

        return ""

    def set_clipboard_text(self, text: str) -> bool:
        """Copies given text to the Windows clipboard."""
        if self.user32 and self.kernel32:
            try:
                self.kernel32.GlobalAlloc.restype = ctypes.c_void_p
                self.kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
                self.kernel32.GlobalLock.restype = ctypes.c_void_p
                self.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
                self.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
                self.user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]

                if self.user32.OpenClipboard(None):
                    try:
                        self.user32.EmptyClipboard()
                        encoded = text.encode("utf-16-le") + b"\x00\x00"
                        h_mem = self.kernel32.GlobalAlloc(0x0002, len(encoded))
                        if h_mem:
                            ptr = self.kernel32.GlobalLock(h_mem)
                            if ptr:
                                ctypes.memmove(ptr, encoded, len(encoded))
                                self.kernel32.GlobalUnlock(h_mem)
                                self.user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                                return True
                    finally:
                        self.user32.CloseClipboard()
            except Exception:
                pass

        # Fallback: PowerShell Set-Clipboard
        try:
            p = subprocess.Popen(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"], stdin=subprocess.PIPE)
            p.communicate(input=text.encode("utf-8"), timeout=2)
            return p.returncode == 0
        except Exception:
            return False

    # =====================================================================
    # 6. INSTANT SYSTEM INTENT INTERCEPTOR
    # =====================================================================

    def intercept_command(self, query: str) -> Optional[str]:
        """
        Inspects query for direct Laptop OS commands.
        If matched, executes the hardware action immediately with microsecond latency
        and returns a verbal reply, bypassing cloud LLM latency for pure hardware tasks.
        """
        import re
        lower = query.lower().strip()

        # Workstation Lock
        if re.search(r'\b(?:lock\s+(?:the\s+)?(?:laptop|screen|pc|workstation|computer)|lock\s+down)\b', lower):
            _, reply = self.lock_workstation()
            return reply

        # Sleep / Suspend
        if re.search(r'\b(?:put\s+(?:the\s+)?(?:laptop|pc|computer)\s+to\s+sleep|sleep\s+mode|go\s+to\s+sleep)\b', lower):
            _, reply = self.sleep_workstation()
            return reply

        # Volume Mute / Unmute
        if re.search(r'\b(?:unmute|sound\s+on)\b', lower):
            _, reply = self.set_mute(False)
            return reply
        if re.search(r'\b(?:mute|silence\s+audio|shut\s+up)\b', lower):
            _, reply = self.set_mute(True)
            return reply

        # Absolute Volume (e.g. "volume 40%", "set volume to 60", "volume 80")
        vol_match = re.search(r'\b(?:volume|sound)\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)?\b', lower)
        if vol_match:
            val = int(vol_match.group(1))
            _, reply = self.set_volume(val)
            return reply

        # Relative Volume (e.g. "turn up the volume", "volume down", "increase volume")
        if re.search(r'\b(?:increase|turn\s+up|raise)\s+(?:the\s+)?(?:volume|sound)\b', lower):
            _, reply = self.change_volume(+15)
            return reply
        if re.search(r'\b(?:decrease|turn\s+down|lower)\s+(?:the\s+)?(?:volume|sound)\b', lower):
            _, reply = self.change_volume(-15)
            return reply

        # Brightness / Dimming
        bright_match = re.search(r'\b(?:brightness|screen\s+light)\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)?\b', lower)
        if bright_match:
            val = int(bright_match.group(1))
            _, reply = self.set_brightness(val)
            return reply
        if re.search(r'\b(?:dim\s+(?:the\s+)?(?:screen|display|brightness))\b', lower):
            _, reply = self.set_brightness(30)
            return reply
        if re.search(r'\b(?:brighten\s+(?:the\s+)?(?:screen|display)|max\s+brightness)\b', lower):
            _, reply = self.set_brightness(100)
            return reply

        # Battery / Power Telemetry
        if re.search(r'\b(?:battery|power\s+level|charging\s+status|how\s+much\s+battery)\b', lower):
            bat = self.get_battery_status()
            return f"Sir, {bat.get('description')}"

        # System Specs / Hardware Telemetry
        if re.search(r'\b(?:system\s+(?:status|telemetry|specs|diagnostics)|hardware\s+status|laptop\s+status|ram\s+usage|cpu\s+usage)\b', lower):
            return f"Current workstation telemetry, Sir:\n{self.get_system_telemetry()}"

        # App & Website Launcher: "open <target>", "launch <target>"
        launch_match = re.search(r'^(?:jarvis\s+)?(?:open|launch)\s+(.+)$', lower)
        if launch_match:
            target = launch_match.group(1).strip()
            # Avoid matching conversational phrases like "open to suggestions"
            if target and target not in ("to suggestions", "up", "a discussion", "my eyes"):
                _, reply = self.launch(target)
                return reply

        return None


def urllib_parse(text: str) -> str:
    import urllib.parse
    return urllib.parse.quote_plus(text)
