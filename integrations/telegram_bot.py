import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
from core.brain import JarvisBrain
from core.memory import MemoryManager
from voice.tts import generate_speech_file
from integrations.google_services import GoogleServices
from core.scheduler import JarvisScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("JarvisTelegram")

brain = JarvisBrain()
memory = MemoryManager()
google = GoogleServices()
scheduler = JarvisScheduler()

def is_authorized(update: Update) -> bool:
    """Verifies that the sender matches TELEGRAM_USER_ID if configured."""
    if not config.TELEGRAM_USER_ID:
        return True
    return str(update.effective_user.id) == str(config.TELEGRAM_USER_ID)

def get_context_for_query(query: str) -> str:
    """Gathers calendar, email, or task context relevant to the user query."""
    lower = query.lower()
    ctx = ""
    if any(k in lower for k in ["schedule", "calendar", "meeting", "events", "agenda"]):
        if google.is_configured():
            ctx += f"\nCurrent Calendar Agenda:\n{google.format_daily_agenda()}\n"
    if any(k in lower for k in ["email", "gmail", "inbox", "mail"]):
        if google.is_configured():
            unreads = google.get_unread_emails(max_results=3)
            ctx += f"\nRecent Unread Emails: {unreads}\n"
    if any(k in lower for k in ["task", "todo", "reminder", "notes"]):
        pending = memory.get_pending_tasks()
        ctx += f"\nPending Tasks in Database: {pending}\n"
    return ctx

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name or config.USER_NAME

    if not config.TELEGRAM_USER_ID:
        config.TELEGRAM_USER_ID = user_id
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "TELEGRAM_USER_ID=" in content:
                content = content.replace("TELEGRAM_USER_ID=", f"TELEGRAM_USER_ID={user_id}")
            else:
                content += f"\nTELEGRAM_USER_ID={user_id}\n"
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)
        logger.info(f"Registered primary user ID: {user_id}")

    welcome = (
        f"🎙️ **Greetings, {user_name}.** {config.ASSISTANT_NAME} is fully online and operational.\n\n"
        f"**Voice & Conversational Abilities:**\n"
        f"• **Send Voice Notes 🗣️** → Speak naturally; I will transcribe your audio and reply in voice.\n"
        f"• **Text Message** → Send any question, command, or instruction.\n"
        f"• `/voice <query>` → Answer any query with a synthesized voice note.\n\n"
        f"**Commands & Integrations:**\n"
        f"• `/briefing` → Deliver a comprehensive spoken & text morning briefing.\n"
        f"• `/agenda` → View upcoming Google Calendar meetings.\n"
        f"• `/emails` → Review unread Gmail messages & urgent alerts.\n"
        f"• `/alert <urgent message>` → Trigger an immediate priority voice alarm.\n"
        f"• `/tasks` → View your task list.\n"
        f"• `/note <text>` → Save a note to long-term memory.\n"
        f"• `/status` → Inspect system diagnostics & status."
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    user_text = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    context_data = await asyncio.to_thread(get_context_for_query, user_text)
    reply = await asyncio.to_thread(brain.ask, user_text, context_data)

    await update.message.reply_text(reply)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming Telegram voice notes and audio files with Gemini speech-to-text and voice reply."""
    if not is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    media = update.message.voice or update.message.audio or update.message.document
    if not media:
        return

    logger.info(f"[*] Received voice/audio message from user {update.effective_user.id}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        media_file = await media.get_file()
        audio_bytes = await media_file.download_as_bytearray()

        raw_mime = getattr(media, "mime_type", "") or "audio/ogg"
        if "ogg" in raw_mime or "opus" in raw_mime:
            mime_type = "audio/ogg"
        elif "mp3" in raw_mime or "mpeg" in raw_mime:
            mime_type = "audio/mp3"
        elif "m4a" in raw_mime or "mp4" in raw_mime or "aac" in raw_mime:
            mime_type = "audio/mp4"
        elif "wav" in raw_mime:
            mime_type = "audio/wav"
        else:
            mime_type = "audio/ogg"

        # Transcribe speech with Gemini
        transcribed_text = await asyncio.to_thread(
            brain.transcribe_audio,
            bytes(audio_bytes),
            mime_type
        )

        if not transcribed_text:
            await update.message.reply_text(
                "Apologies, Sir. I was unable to transcribe your audio message. "
                "Could you please repeat that, or send it in text?"
            )
            return

        # Prepare context and query brain
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        context_data = await asyncio.to_thread(get_context_for_query, transcribed_text)
        reply = await asyncio.to_thread(brain.ask, transcribed_text, context_data)

        # Synthesize spoken response with timeout fallback
        audio_sent = False
        try:
            audio_path = await asyncio.wait_for(
                generate_speech_file(reply, filename=f"reply_voice_{update.message.id}.mp3"),
                timeout=12.0
            )
            caption = f"🗣️ *\"{transcribed_text}\"*\n\n{reply}"
            with open(audio_path, "rb") as audio:
                if len(caption) <= 1024:
                    try:
                        await update.message.reply_voice(voice=audio, caption=caption, parse_mode="Markdown")
                        audio_sent = True
                    except Exception:
                        await update.message.reply_voice(voice=audio, caption=caption, parse_mode=None)
                        audio_sent = True
                else:
                    await update.message.reply_voice(voice=audio, caption=f"🗣️ *\"{transcribed_text}\"*", parse_mode=None)
                    await update.message.reply_text(reply)
                    audio_sent = True
        except Exception as tts_err:
            logger.warning(f"TTS voice synthesis timed out or failed ({tts_err}), responding in text.")

        if not audio_sent:
            await update.message.reply_text(f"🗣️ *\"{transcribed_text}\"*\n\n{reply}")

    except Exception as e:
        logger.error(f"[-] Error processing incoming voice/audio message: {e}", exc_info=True)
        await update.message.reply_text(f"Apologies, Sir. An error occurred processing your audio: {e}")

async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delivers an on-demand audio and text briefing."""
    if not is_authorized(update):
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    briefing_text = await scheduler.compile_briefing_text()
    clean_spoken = (
        f"Sir, here is your briefing. "
        f"{briefing_text.replace('*', '').replace('`', '').replace('•', '')}"
    )
    try:
        audio_path = await generate_speech_file(clean_spoken[:500], filename=f"briefing_{update.message.id}.mp3")
        with open(audio_path, "rb") as audio:
            await update.message.reply_voice(voice=audio, caption=briefing_text[:1024], parse_mode="Markdown")
    except Exception as e:
        logger.error(f"[-] Voice synthesis failed for briefing: {e}")
        await update.message.reply_text(briefing_text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays system status diagnostics."""
    if not is_authorized(update):
        return
    cal_status = "🟢 Connected (Auto-refresh enabled)" if google.is_configured() else "🔴 Disconnected"
    gemini_status = "🟢 Configured" if config.GEMINI_API_KEY else "🔴 Missing Key"
    tasks_count = len(memory.get_pending_tasks())

    msg = (
        f"🛡️ **{config.ASSISTANT_NAME} System Diagnostics:**\n\n"
        f"• **Cognitive Engine (Gemini)**: {gemini_status}\n"
        f"• **Vocal Synthesis (Edge-TTS)**: 🟢 Active (en-GB-RyanNeural)\n"
        f"• **Voice Recognition**: 🟢 Multimodal Audio Active\n"
        f"• **Google Workspace**: {cal_status}\n"
        f"• **Autonomous Scheduler**: 🟢 Active (Briefings & Guardians)\n"
        f"• **Memory Database**: 🟢 Connected ({tasks_count} pending tasks)\n"
        f"• **Primary User ID**: `{config.TELEGRAM_USER_ID or 'Not Set'}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def agenda_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not google.is_configured():
        await update.message.reply_text(
            "⚠️ Google Calendar is not yet linked, Sir.\nPlease add credentials.json to enable calendar syncing."
        )
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    agenda = await asyncio.to_thread(google.format_daily_agenda)
    await update.message.reply_text(f"📅 **Calendar Agenda:**\n{agenda}")

async def emails_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not google.is_configured():
        await update.message.reply_text(
            "⚠️ Gmail is not yet linked, Sir.\nPlease add credentials.json to enable email syncing."
        )
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    emails = await asyncio.to_thread(google.get_unread_emails, 5)
    if not emails:
        await update.message.reply_text("📭 Inbox zero! You have no unread emails, Sir.")
        return
    msg = f"📬 **Unread Emails ({len(emails)}):**\n\n"
    for em in emails:
        msg += f"• **From:** {em['from']}\n  **Subject:** {em['subject']}\n  _{em['snippet'][:100]}..._\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_voice_reply_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    query = " ".join(context.args) if context.args else "Report current status and readiness."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")

    context_data = await asyncio.to_thread(get_context_for_query, query)
    reply = await asyncio.to_thread(brain.ask, query, context_data)
    audio_path = await generate_speech_file(reply, filename=f"reply_{update.message.id}.mp3")

    with open(audio_path, "rb") as audio:
        await update.message.reply_voice(voice=audio, caption=reply)

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    alert_msg = " ".join(context.args) if context.args else "Attention Sir: Urgent action required!"
    spoken_text = f"Sir, urgent alert: {alert_msg}"

    audio_path = await generate_speech_file(spoken_text, filename="urgent_alert.mp3")

    with open(audio_path, "rb") as audio:
        await update.message.reply_voice(
            voice=audio,
            caption=f"🚨 **URGENT ALARM** 🚨\n{alert_msg}"
        )

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    note_text = " ".join(context.args)
    if not note_text:
        await update.message.reply_text("Usage: `/note your note content here`", parse_mode="Markdown")
        return
    note_id = await asyncio.to_thread(memory.add_note, note_text)
    await update.message.reply_text(f"📝 Note saved (ID #{note_id}):\n_{note_text}_", parse_mode="Markdown")

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    tasks = await asyncio.to_thread(memory.get_pending_tasks)
    if not tasks:
        await update.message.reply_text("✅ No pending tasks, Sir. Your slate is clean.")
        return
    msg = "📋 **Pending Tasks:**\n"
    for t in tasks:
        urgency = " 🔴 [URGENT]" if t.get("is_urgent") else ""
        due = f" (Due: {t.get('due_date')})" if t.get("due_date") else ""
        msg += f"• #{t['id']}: {t['title']}{urgency}{due}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

from telegram.request import HTTPXRequest
from aiohttp import web

async def health_check_handler(request):
    return web.Response(text="🟢 Jarvis Assistant Service is operational.")

async def start_health_server():
    """Lightweight HTTP server on $PORT for cloud platforms (Render, Koyeb, etc.)."""
    port_str = os.environ.get("PORT")
    if not port_str:
        return
    try:
        port = int(port_str)
        app = web.Application()
        app.router.add_get("/", health_check_handler)
        app.router.add_get("/health", health_check_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"[+] Health check server listening on port {port}")
    except Exception as e:
        logger.error(f"[-] Could not start cloud health check server: {e}")

async def on_post_init(app):
    """Initializes background scheduler loop and health server upon application startup."""
    scheduler.bot_app = app
    asyncio.create_task(scheduler.run_loop())
    asyncio.create_task(start_health_server())
    logger.info("[+] Autonomous Scheduler & Cloud Health check registered with event loop.")

from telegram.request import HTTPXRequest

def build_telegram_application():
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("\n[!] TELEGRAM_BOT_TOKEN is not configured in .env.")
        return None

    request = HTTPXRequest(connect_timeout=20.0, read_timeout=30.0)
    app = ApplicationBuilder().token(token).request(request).post_init(on_post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("voice", handle_voice_reply_request))
    app.add_handler(CommandHandler("agenda", agenda_command))
    app.add_handler(CommandHandler("emails", emails_command))
    app.add_handler(CommandHandler("alert", alert_command))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("tasks", tasks_command))
    app.add_handler(CommandHandler("briefing", briefing_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.Document.AUDIO, handle_voice_message))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    return app

def start_telegram_service():
    app = build_telegram_application()
    if not app:
        return

    print("\n" + "=" * 55)
    print("[+] Jarvis Telegram Service is LIVE and listening for commands!")
    print("=" * 55 + "\n")
    app.run_polling(bootstrap_retries=5, poll_interval=1.0)

if __name__ == "__main__":
    start_telegram_service()
