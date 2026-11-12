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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("JarvisTelegram")

brain = JarvisBrain()
memory = MemoryManager()
google = GoogleServices()

def is_authorized(update: Update) -> bool:
    """Verifies that the sender matches TELEGRAM_USER_ID if configured."""
    if not config.TELEGRAM_USER_ID:
        return True
    return str(update.effective_user.id) == str(config.TELEGRAM_USER_ID)

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
        f"🎙️ **Greetings, {user_name}.** {config.ASSISTANT_NAME} is online and operational.\n\n"
        f"**Commands at your disposal:**\n"
        f"• Send any question/instruction → I will assist you.\n"
        f"• `/voice <query>` → I will answer with a spoken voice note.\n"
        f"• `/agenda` → View your upcoming Google Calendar meetings.\n"
        f"• `/emails` → Review unread Gmail messages & urgent alerts.\n"
        f"• `/alert <urgent message>` → Trigger an urgent priority alarm.\n"
        f"• `/tasks` → View your task list.\n"
        f"• `/note <text>` → Save a note to long-term memory.\n"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    user_text = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    context_data = ""
    lower = user_text.lower()

    def fetch_context():
        ctx = ""
        if any(k in lower for k in ["schedule", "calendar", "meeting", "events", "agenda"]):
            if google.is_configured():
                ctx += f"\nCurrent Calendar Agenda:\n{google.format_daily_agenda()}\n"
        if any(k in lower for k in ["email", "gmail", "inbox", "mail"]):
            if google.is_configured():
                unreads = google.get_unread_emails(max_results=3)
                ctx += f"\nRecent Unread Emails: {unreads}\n"
        return ctx

    # Run blocking I/O in thread to prevent blocking asyncio loop
    context_data = await asyncio.to_thread(fetch_context)
    reply = await asyncio.to_thread(brain.ask, user_text, context_data)

    await update.message.reply_text(reply)

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

    reply = await asyncio.to_thread(brain.ask, query, "")
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

def start_telegram_service():
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("\n[!] TELEGRAM_BOT_TOKEN is not configured in .env.")
        return

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("voice", handle_voice_reply_request))
    app.add_handler(CommandHandler("agenda", agenda_command))
    app.add_handler(CommandHandler("emails", emails_command))
    app.add_handler(CommandHandler("alert", alert_command))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("tasks", tasks_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

    print("\n" + "=" * 55)
    print("[+] Jarvis Telegram Service is LIVE and listening for commands!")
    print("=" * 55 + "\n")
    app.run_polling()

if __name__ == "__main__":
    start_telegram_service()
