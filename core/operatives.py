"""
Operatives Subsystem (Inspired by OpenJarvis)
=============================================
Autonomous, lightweight background workers that:
1. Warm up & cache calendar, email, and daily briefing context in RAM for sub-second voice queries.
2. Monitor workstation hardware (battery, power, memory) and proactively alert the user.
"""
import time
import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger("JarvisOperatives")

class ContextCacheOperative:
    """
    Keeps fresh Calendar, Email, and Briefing data pre-loaded in memory.
    Ensures voice questions like 'What is my schedule?' answer in < 0.2s without API lag.
    """
    def __init__(self, google_services=None, memory_manager=None, refresh_interval: int = 900):
        self.google = google_services
        self.memory = memory_manager
        self.refresh_interval = refresh_interval  # Refresh every 15 minutes
        self.cache: Dict[str, Any] = {
            "agenda": "",
            "unreads": "",
            "pending_tasks": "",
            "last_updated": 0
        }
        self.lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ContextCacheOperative")
        self._thread.start()
        logger.info("[+] ContextCacheOperative active.")

    def stop(self):
        self._running = False

    def _refresh(self):
        try:
            agenda_txt = ""
            unreads_txt = ""
            if self.google and self.google.is_configured():
                agenda_txt = self.google.format_daily_agenda()
                unreads_txt = str(self.google.get_unread_emails(max_results=3))

            tasks_txt = ""
            if self.memory:
                tasks_txt = str(self.memory.get_pending_tasks())

            with self.lock:
                self.cache["agenda"] = agenda_txt
                self.cache["unreads"] = unreads_txt
                self.cache["pending_tasks"] = tasks_txt
                self.cache["last_updated"] = time.time()
            logger.debug("[Operatives] Cache refreshed with fresh Google & Task context.")
        except Exception as e:
            logger.debug(f"[Operatives] Context refresh skipped: {e}")

    def _run_loop(self):
        # Initial immediate warm-up in background
        time.sleep(1.0)
        self._refresh()
        while self._running:
            time.sleep(self.refresh_interval)
            if self._running:
                self._refresh()

    def get_agenda(self) -> str:
        with self.lock:
            # If cache is populated, return instantly
            if self.cache["agenda"]:
                return self.cache["agenda"]
        # Fallback to direct fetch if cold
        if self.google and self.google.is_configured():
            return self.google.format_daily_agenda()
        return ""

    def get_unreads(self) -> str:
        with self.lock:
            if self.cache["unreads"]:
                return self.cache["unreads"]
        if self.google and self.google.is_configured():
            return str(self.google.get_unread_emails(max_results=3))
        return ""

    def get_pending_tasks(self) -> str:
        with self.lock:
            if self.cache["pending_tasks"]:
                return self.cache["pending_tasks"]
        if self.memory:
            return str(self.memory.get_pending_tasks())
        return ""


class HardwareWatchdogOperative:
    """
    Watches laptop battery level, charging status, and memory load.
    Proactively triggers voice alerts or HUD warnings when battery gets low.
    """
    def __init__(self, system_commander, speak_callback=None, notify_callback=None, poll_interval: int = 60):
        self.cmd = system_commander
        self.speak = speak_callback
        self.notify = notify_callback
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # State tracking to avoid repetitive alerts
        self._last_alert_level: Optional[int] = None
        self._was_charging: Optional[bool] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HardwareWatchdogOperative")
        self._thread.start()
        logger.info("[+] HardwareWatchdogOperative active.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        time.sleep(10.0)  # Settle time after boot
        while self._running:
            try:
                bat = self.cmd.get_battery_status()
                percent = bat.get("percent")
                charging = bat.get("charging")

                if percent is not None:
                    # Low battery alert: <= 20% and discharging
                    if not charging and percent <= 20:
                        if self._last_alert_level is None or percent <= self._last_alert_level - 5:
                            self._last_alert_level = percent
                            msg = f"Sir, battery is down to {percent} percent. Please plug in the workstation."
                            logger.info(f"⚠️ [PROACTIVE ALERT] {msg}")
                            if self.notify:
                                self.notify("⚠️ Low Battery", msg)
                            if self.speak:
                                self.speak(msg)
                    elif charging:
                        # Reset low battery trigger once plugged in
                        self._last_alert_level = None

                    # Detect unplugged event
                    if self._was_charging is True and charging is False and percent <= 35:
                        msg = f"Workstation running on battery power. Remaining capacity is {percent} percent."
                        logger.info(f"🔌 [PROACTIVE] {msg}")
                        if self.notify:
                            self.notify("🔌 Power Unplugged", msg)

                    self._was_charging = charging
            except Exception as e:
                logger.debug(f"[Watchdog] Error checking battery: {e}")

            time.sleep(self.poll_interval)
