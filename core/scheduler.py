import asyncio
import datetime
import logging
from typing import Set, Optional, Dict, Any
from pathlib import Path

import config
from core.brain import JarvisBrain
from core.memory import MemoryManager
from voice.tts import generate_speech_file
from integrations.google_services import GoogleServices

logger = logging.getLogger("JarvisScheduler")

class JarvisScheduler:
    """
    Autonomous background monitoring engine for Jarvis.
    Proactively checks:
    - Upcoming calendar events (15-min warning)
    - High-urgency unread emails
    - Daily morning briefings
    - Urgent task reminders
    """

    def __init__(self, bot_app=None, briefing_hour: int = 8, briefing_minute: int = 0):
        self.bot_app = bot_app
        self.google = GoogleServices()
        self.memory = MemoryManager()
        self.brain = JarvisBrain()
        self.briefing_hour = briefing_hour
        self.briefing_minute = briefing_minute

        self._alerted_event_ids: Set[str] = set()
        self._alerted_email_ids: Set[str] = set()
        self._last_briefing_date: Optional[datetime.date] = None
        self._is_running = False

    async def send_user_message(self, text: str, parse_mode: str = "Markdown"):
        """Sends a text message to the primary Telegram user."""
        if not self.bot_app or not config.TELEGRAM_USER_ID:
            logger.info(f"[Scheduler Message]: {text}")
            return
        try:
            await self.bot_app.bot.send_message(
                chat_id=config.TELEGRAM_USER_ID,
                text=text,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"[-] Failed to send Telegram message from scheduler: {e}")

    async def send_user_voice(self, audio_path: Path, caption: str = ""):
        """Sends a voice note with caption to the primary Telegram user."""
        if not self.bot_app or not config.TELEGRAM_USER_ID:
            logger.info(f"[Scheduler Voice]: {caption}")
            return
        try:
            with open(audio_path, "rb") as audio:
                await self.bot_app.bot.send_voice(
                    chat_id=config.TELEGRAM_USER_ID,
                    voice=audio,
                    caption=caption
                )
        except Exception as e:
            logger.error(f"[-] Failed to send Telegram voice from scheduler: {e}")

    async def compile_briefing_text(self) -> str:
        """Compiles a full daily briefing summary."""
        now = datetime.datetime.now()
        greeting = "Good morning" if now.hour < 12 else ("Good afternoon" if now.hour < 17 else "Good evening")
        date_str = now.strftime("%A, %B %d, %Y")

        briefing = f"🌅 **{greeting}, {config.USER_NAME}.**\nHere is your Jarvis briefing for {date_str}.\n\n"

        # 1. Calendar agenda
        if self.google.is_configured():
            events = await asyncio.to_thread(self.google.get_upcoming_events, 5)
            if events:
                briefing += "📅 **Today's Agenda:**\n"
                for ev in events:
                    briefing += f"• `{ev['start']}` — **{ev['summary']}**\n"
            else:
                briefing += "📅 **Schedule:** No upcoming meetings. Your calendar is clear, Sir.\n"
        else:
            briefing += "📅 **Schedule:** Calendar is not connected.\n"

        briefing += "\n"

        # 2. Email highlights
        if self.google.is_configured():
            emails = await asyncio.to_thread(self.google.get_unread_emails, 3)
            urgent = await asyncio.to_thread(self.google.check_urgent_emails, 5)
            if urgent:
                briefing += f"🚨 **Urgent Emails ({len(urgent)}):**\n"
                for em in urgent:
                    briefing += f"• **{em['from']}**: {em['subject']}\n"
            elif emails:
                briefing += f"📬 **Unread Emails ({len(emails)}):**\n"
                for em in emails:
                    briefing += f"• **{em['from']}**: {em['subject']}\n"
            else:
                briefing += "📬 **Inbox:** Inbox zero! No unread messages.\n"
        briefing += "\n"

        # 3. Pending urgent tasks
        tasks = await asyncio.to_thread(self.memory.get_pending_tasks, True)
        if tasks:
            briefing += f"⚠️ **Urgent Tasks Requiring Attention ({len(tasks)}):**\n"
            for t in tasks:
                briefing += f"• #{t['id']}: {t['title']}\n"
        else:
            all_tasks = await asyncio.to_thread(self.memory.get_pending_tasks, False)
            if all_tasks:
                briefing += f"📋 **Pending Tasks:** {len(all_tasks)} item(s) in queue.\n"
            else:
                briefing += "✅ **Tasks:** All tasks are up to date.\n"

        briefing += f"\nAt your service, {config.USER_NAME}."
        return briefing

    async def deliver_daily_briefing(self):
        """Generates and delivers the morning briefing via Telegram (both Voice and Text)."""
        briefing_text = await self.compile_briefing_text()
        spoken_text = (
            f"Good morning, {config.USER_NAME}. Here is your morning briefing. "
            f"{briefing_text.replace('*', '').replace('`', '').replace('•', '')}"
        )
        try:
            audio_path = await generate_speech_file(spoken_text[:500], filename="morning_briefing.mp3")
            await self.send_user_voice(audio_path, caption=briefing_text[:1024])
        except Exception as e:
            logger.error(f"[-] Voice synthesis failed for briefing: {e}")
            await self.send_user_message(briefing_text)

    async def check_upcoming_meetings(self):
        """Scans Google Calendar for events starting in 10-15 minutes."""
        if not self.google.is_configured():
            return
        events = await asyncio.to_thread(self.google.get_upcoming_events, 5)
        now = datetime.datetime.now(datetime.timezone.utc)

        for ev in events:
            ev_id = ev.get("id") or ev.get("summary")
            if ev_id in self._alerted_event_ids:
                continue

            start_str = ev.get("start")
            if not start_str:
                continue

            try:
                # Handle dateTime format
                clean_start = start_str.replace("Z", "+00:00")
                if "T" in clean_start:
                    ev_dt = datetime.datetime.fromisoformat(clean_start)
                    # If timezone naive, make UTC
                    if ev_dt.tzinfo is None:
                        ev_dt = ev_dt.replace(tzinfo=datetime.timezone.utc)
                    delta_seconds = (ev_dt - now).total_seconds()
                    alert_window = int(self.memory.get_setting("meeting_alert_minutes", "15")) * 60
                    # Alert if meeting starts between 0 and alert_window seconds from now
                    if 0 <= delta_seconds <= alert_window:
                        mins_left = max(1, int(delta_seconds // 60))
                        msg = (
                            f"🔔 **Upcoming Meeting in ~{mins_left} minutes!**\n"
                            f"• **Event:** {ev.get('summary')}\n"
                            f"• **Starts at:** {ev.get('start')}"
                        )
                        if ev.get("location"):
                            msg += f"\n• **Location:** {ev['location']}"
                        self._alerted_event_ids.add(ev_id)
                        await self.send_user_message(msg)
            except Exception as e:
                logger.debug(f"Error parsing event start time ({start_str}): {e}")

    async def check_urgent_emails(self):
        """Scans unread emails and alerts immediately if high priority."""
        if not self.google.is_configured():
            return
        urgent_emails = await asyncio.to_thread(self.google.check_urgent_emails, 5)
        for em in urgent_emails:
            em_id = em.get("id") or (em.get("from", "") + em.get("subject", ""))
            if em_id in self._alerted_email_ids:
                continue

            self._alerted_email_ids.add(em_id)
            spoken = f"Sir, urgent email received from {em.get('from')}. Subject: {em.get('subject')}."
            msg = (
                f"🚨 **URGENT EMAIL DETECTED** 🚨\n\n"
                f"• **From:** {em.get('from')}\n"
                f"• **Subject:** {em.get('subject')}\n"
                f"• **Snippet:** _{em.get('snippet')}_"
            )
            try:
                audio_path = await generate_speech_file(spoken, filename=f"urgent_{em_id[:8]}.mp3")
                await self.send_user_voice(audio_path, caption=msg)
            except Exception:
                await self.send_user_message(msg)

    async def run_loop(self):
        """Main autonomous scheduler loop running periodically."""
        self._is_running = True
        logger.info("[+] Autonomous Jarvis Scheduler started.")

        cycle_count = 0
        while self._is_running:
            try:
                now = datetime.datetime.now()

                # 1. Morning briefing trigger (once per day, dynamically configured)
                briefing_h = int(self.memory.get_setting("briefing_hour", "8"))
                briefing_m = int(self.memory.get_setting("briefing_minute", "0"))
                if (now.hour == briefing_h and
                    now.minute >= briefing_m and
                    self._last_briefing_date != now.date()):
                    self._last_briefing_date = now.date()
                    logger.info("[*] Delivering automated morning briefing...")
                    await self.deliver_daily_briefing()

                # 2. Upcoming meeting alerts (every minute)
                await self.check_upcoming_meetings()

                # 3. Urgent email checks (every 5 cycles ~ 5 mins)
                if cycle_count % 5 == 0:
                    await self.check_urgent_emails()

            except Exception as e:
                logger.error(f"[-] Error in scheduler cycle: {e}")

            cycle_count += 1
            await asyncio.sleep(60)

    def stop(self):
        self._is_running = False
