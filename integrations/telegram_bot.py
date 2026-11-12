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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("JarvisTelegram")

brain = JarvisBrain()
memory = MemoryManager()

def is_authorized(update: Update) -> bool:
    """Verifies that the sender matches TELEGRAM_USER_ID if configured."""
    if not config.TELEGRAM_USER_ID:
        return True
    return str(update.effective_user.id) == str(config.TELEGRAM_USER_ID)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name or config.USER_NAME

    # If TELEGRAM_USER_ID is not configured yet, save it to .env
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
        f"🎙️ **Greetings, {user_name}.** {config.ASSISTANT_NAME} is online and paired to this device.\n\n"
        f"**Commands you can use:**\n"
        f"• Send any text or question → I will answer.\n"
        f"• `/voice <text>` → I will respond with a spoken voice note.\n"
        f"• `/note <text>` → Save a quick note to long-term memory.\n"
        f"• `/tasks` → View your pending tasks and reminders.\n"
        f"• `/alert <urgent message>` → Trigger an urgent priority alarm with voice.\n"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    user_text = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Ask Jarvis Brain
    reply = brain.ask(user_text)
    await update.message.reply_text(reply)

async def handle_voice_reply_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answers the user query with both text AND a spoken voice note."""
    if not is_authorized(update):
        return

    query = " ".join(context.args) if context.args else "Report current status and readiness."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")

    reply = brain.ask(query)
    # Generate audio
    audio_path = await generate_speech_file(reply, filename=f"reply_{update.message.id}.mp3")

    # Send audio voice note
    with open(audio_path, "rb") as audio:
        await update.message.reply_voice(voice=audio, caption=reply)

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simulates an urgent call/alarm with priority notification and voice message."""
    if not is_authorized(update):
        return

    alert_msg = " ".join(context.args) if context.args else "Attention Sir: Urgent action required!"
    spoken_text = f"Sir, urgent alert: {alert_msg}"

    # Generate urgent audio
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
    note_id = memory.add_note(note_text)
    await update.message.reply_text(f"📝 Note saved (ID #{note_id}):\n_{note_text}_", parse_mode="Markdown")

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    tasks = memory.get_pending_tasks()
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
        print("    1. Open Telegram and search for @BotFather")
        print("    2. Send '/newbot', give it a name (e.g. 'MyJarvisBot') and a username")
        print("    3. Copy the HTTP API token BotFather gives you")
        print("    4. Paste it into your .env file: TELEGRAM_BOT_TOKEN=your_token_here\n")
        return

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("voice", handle_voice_reply_request))
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
