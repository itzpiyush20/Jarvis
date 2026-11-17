import asyncio
import datetime
import html
import logging
from typing import Set, Optional, Dict, Any
from pathlib import Path

import config
from core.brain import JarvisBrain
from core.memory import MemoryManager
from voice.tts import generate_speech_file
from integrations.google_services import GoogleServices

logger = logging.getLogger("JarvisScheduler")

# Indian Standard Time (UTC+5:30) for scheduled briefings and alerts
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

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
        self._alerted_low_battery: bool = False
        self._last_briefing_date: Optional[datetime.date] = None
        self._is_running = False

    async def send_user_message(self, text: str, parse_mode: Optional[str] = "HTML"):
        """Sends a text message to the primary Telegram user with safe HTML parsing and fallback."""
        if not self.bot_app or not config.TELEGRAM_USER_ID:
            logger.info(f"[Scheduler Message]: {text}")
            return

        formatted = text
        if parse_mode == "HTML" and not ("<b>" in text or "<code>" in text or "<pre>" in text):
            try:
                from integrations.telegram_bot import format_to_telegram_html
                formatted = format_to_telegram_html(text)
            except Exception:
                formatted = html.escape(text)

        try:
            await self.bot_app.bot.send_message(
                chat_id=config.TELEGRAM_USER_ID,
                text=formatted,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.warning(f"Scheduler HTML send failed ({e}), falling back to plain text...")
            try:
                await self.bot_app.bot.send_message(
                    chat_id=config.TELEGRAM_USER_ID,
                    text=text,
                    parse_mode=None
                )
            except Exception as e2:
                logger.error(f"[-] Failed to send Telegram message from scheduler: {e2}")

    async def send_user_voice(self, audio_path: Path, caption: str = "", parse_mode: Optional[str] = "HTML"):
        """Sends a voice note with formatted caption to the primary Telegram user."""
        if not self.bot_app or not config.TELEGRAM_USER_ID:
            logger.info(f"[Scheduler Voice]: {caption}")
            return

        formatted_caption = caption
        if parse_mode == "HTML" and caption and not ("<b>" in caption or "<code>" in caption or "<i>" in caption):
            try:
                from integrations.telegram_bot import format_to_telegram_html
                formatted_caption = format_to_telegram_html(caption)
            except Exception:
                formatted_caption = html.escape(caption)

        try:
            with open(audio_path, "rb") as audio:
                await self.bot_app.bot.send_voice(
                    chat_id=config.TELEGRAM_USER_ID,
                    voice=audio,
                    caption=formatted_caption[:1024] if formatted_caption else None,
                    parse_mode=parse_mode
                )
        except Exception as e:
            logger.warning(f"Scheduler voice send with {parse_mode} caption failed ({e}), falling back to plain text...")
            try:
                with open(audio_path, "rb") as audio:
                    await self.bot_app.bot.send_voice(
                        chat_id=config.TELEGRAM_USER_ID,
                        voice=audio,
                        caption=caption[:1024] if caption else None,
                        parse_mode=None
                    )
            except Exception as e2:
                logger.error(f"[-] Failed to send Telegram voice from scheduler: {e2}")

    async def compile_briefing_text(self) -> str:
        """Compiles a full daily briefing summary in Indian Standard Time (IST)."""
        now = datetime.datetime.now(IST)
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
            await self.send_user_voice(audio_path, caption=briefing_text[:1024], parse_mode="HTML")
        except Exception as e:
            logger.error(f"[-] Voice synthesis failed for briefing: {e}")
            await self.send_user_message(briefing_text, parse_mode="HTML")

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
                        clean_summary = html.escape(str(ev.get('summary', 'Untitled Meeting')))
                        clean_start_display = html.escape(str(ev.get('start', '')))
                        msg = (
                            f"🔔 <b>Upcoming Meeting in ~{mins_left} minutes!</b>\n"
                            f"• <b>Event:</b> {clean_summary}\n"
                            f"• <b>Starts at:</b> <code>{clean_start_display}</code>"
                        )
                        if ev.get("location"):
                            clean_loc = html.escape(str(ev.get("location")))
                            msg += f"\n• <b>Location:</b> {clean_loc}"
                        self._alerted_event_ids.add(ev_id)
                        await self.send_user_message(msg, parse_mode="HTML")
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
            clean_from = html.escape(str(em.get('from', 'Unknown Sender')))
            clean_subj = html.escape(str(em.get('subject', 'No Subject')))
            clean_snip = html.escape(str(em.get('snippet', '')[:120]))
            msg = (
                f"🚨 <b>URGENT EMAIL DETECTED</b> 🚨\n\n"
                f"• <b>From:</b> {clean_from}\n"
                f"• <b>Subject:</b> {clean_subj}\n"
                f"• <b>Snippet:</b> <i>{clean_snip}...</i>"
            )
            try:
                audio_path = await generate_speech_file(spoken, filename=f"urgent_{em_id[:8]}.mp3")
                await self.send_user_voice(audio_path, caption=msg, parse_mode="HTML")
            except Exception:
                await self.send_user_message(msg, parse_mode="HTML")

    async def check_battery_status(self):
        """Scans laptop power status and alerts when battery drops below 20% on discharge."""
        bat = await asyncio.to_thread(self.brain.system_commander.get_battery_status)
        if not bat.get("available") or not bat.get("is_laptop"):
            return

        percent = bat.get("percent", 100)
        is_plugged = bat.get("is_plugged", True)

        if is_plugged:
            self._alerted_low_battery = False
            return

        if percent <= 20 and not self._alerted_low_battery:
            self._alerted_low_battery = True
            spoken = f"Sir, critical power warning. Battery is at {percent}%. Please connect your charger immediately."
            msg = (
                f"🪫 <b>LOW BATTERY WARNING</b> 🪫\n\n"
                f"• <b>Level:</b> <code>{percent}%</code>\n"
                f"• <b>Status:</b> Discharging on battery power\n\n"
                f"<i>Please connect your laptop to AC power, Sir.</i>"
            )
            try:
                audio_path = await generate_speech_file(spoken, filename="low_battery_alert.mp3")
                await self.send_user_voice(audio_path, caption=msg, parse_mode="HTML")
            except Exception:
                await self.send_user_message(msg, parse_mode="HTML")

    async def run_loop(self):
        """Main autonomous scheduler loop running periodically in IST."""
        self._is_running = True
        logger.info("[+] Autonomous Jarvis Scheduler started (IST timezone calibrated).")

        cycle_count = 0
        while self._is_running:
            try:
                now = datetime.datetime.now(IST)

                # 1. Morning briefing trigger (once per day, dynamically configured in IST)
                briefing_h = int(self.memory.get_setting("briefing_hour", "8"))
                briefing_m = int(self.memory.get_setting("briefing_minute", "0"))
                if (now.hour == briefing_h and
                    now.minute >= briefing_m and
                    self._last_briefing_date != now.date()):
                    self._last_briefing_date = now.date()
                    logger.info("[*] Delivering automated morning briefing (IST)...")
                    await self.deliver_daily_briefing()

                # 2. Upcoming meeting alerts (every minute)
                await self.check_upcoming_meetings()

                # 3. Urgent email checks (every 5 cycles ~ 5 mins)
                if cycle_count % 5 == 0:
                    await self.check_urgent_emails()

                # 4. Low battery power check (every 3 cycles ~ 3 mins)
                if cycle_count % 3 == 0:
                    await self.check_battery_status()

            except Exception as e:
                logger.error(f"[-] Error in scheduler cycle: {e}")

            cycle_count += 1
            await asyncio.sleep(60)

    def stop(self):
        self._is_running = False
