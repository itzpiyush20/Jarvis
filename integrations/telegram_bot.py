import asyncio
import logging
from pathlib import Path
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
from voice.tts import generate_speech_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JarvisTelegram")

brain = JarvisBrain()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    logger.info(f"Connected from User ID: {user_id}")
    welcome_text = (
        f"Greetings, {config.USER_NAME}. {config.ASSISTANT_NAME} is active.\n\n"
        f"Your Telegram User ID is: `{user_id}`\n"
        f"(Add this to your `.env` as `TELEGRAM_USER_ID={user_id}` to secure your assistant).\n\n"
        "You can send me text messages or voice notes anytime."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    # Security check: ignore messages from unknown users if TELEGRAM_USER_ID is set
    if config.TELEGRAM_USER_ID and user_id != config.TELEGRAM_USER_ID:
        await update.message.reply_text("Access denied: unauthorized user.")
        return

    user_text = update.message.text
    # Get answer from Jarvis Brain
    reply_text = brain.ask(user_text)

    # Reply with text
    await update.message.reply_text(reply_text)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if config.TELEGRAM_USER_ID and user_id != config.TELEGRAM_USER_ID:
        return

    # In future turns we can plug in STT directly for voice notes
    await update.message.reply_text("Voice note received, processing, sir...")

def run_bot():
    if not config.TELEGRAM_BOT_TOKEN:
        print("[!] TELEGRAM_BOT_TOKEN is missing in .env. Bot will not start.")
        return
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    print("[*] Jarvis Telegram Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    run_bot()
