import asyncio
import logging
import os
import sys
import html
import re
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
from telegram.request import HTTPXRequest
from aiohttp import web

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

def format_to_telegram_html(text: str) -> str:
    """Converts CommonMark markdown into clean, beautiful, safe Telegram HTML."""
    if not text:
        return ""

    # Protect code blocks
    code_blocks = []
    def save_code_block(match):
        code_blocks.append(match.group(1))
        return f"%%CODE_BLOCK_{len(code_blocks)-1}%%"
    text = re.sub(r'```(?:[a-zA-Z0-9_-]+)?\n?(.*?)```', save_code_block, text, flags=re.DOTALL)

    inline_codes = []
    def save_inline_code(match):
        inline_codes.append(match.group(1))
        return f"%%INLINE_CODE_{len(inline_codes)-1}%%"
    text = re.sub(r'`([^`]+)`', save_inline_code, text)

    # Escape HTML special characters
    text = html.escape(text)

    # Convert headers (# Header) to bold
    text = re.sub(r'^(?:#{1,3})\s*(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Convert **bold** or __bold__ to <b>...</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Convert *italic* or _italic_ to <i>...</i>
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', text)

    # Bullet lists: normalize "- " or "* " to clean unicode bullet "• "
    text = re.sub(r'^\s*[-*]\s+', '• ', text, flags=re.MULTILINE)

    # Restore code blocks
    for i, code in enumerate(code_blocks):
        escaped_code = html.escape(code.strip())
        text = text.replace(f"%%CODE_BLOCK_{i}%%", f"<pre>{escaped_code}</pre>")
    for i, code in enumerate(inline_codes):
        escaped_code = html.escape(code)
        text = text.replace(f"%%INLINE_CODE_{i}%%", f"<code>{escaped_code}</code>")

    return text

async def send_safe_html_reply(update: Update, text: str):
    """Sends a message using clean Telegram HTML with safe plain-text fallback."""
    formatted = format_to_telegram_html(text)
    try:
        await update.message.reply_text(formatted, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"HTML parse failed ({e}), sending plain text.")
        await update.message.reply_text(text)

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

    loc = brain.location_manager.get_user_location()

    welcome = (
        f"🎙️ **Greetings, {user_name}.** {config.ASSISTANT_NAME} is fully online and operational.\n\n"
        f"📍 **Calibrated Location:** `{loc['display']}`\n\n"
        f"**Voice & Conversational Abilities:**\n"
        f"• **Send Voice Notes 🗣️** → Speak naturally; I will transcribe your audio and reply in voice.\n"
        f"• **Text Message** → Send any question, command, search, or instruction.\n"
        f"• **Share Location Pin 📍** → Drop your Telegram location pin anytime to recalibrate regional context.\n"
        f"• `/voice <query>` → Answer any query with a synthesized voice note.\n\n"
        f"**Commands & Real-Time Intelligence:**\n"
        f"• `/briefing` → Deliver a comprehensive spoken & text morning briefing.\n"
        f"• `/agenda` → View upcoming Google Calendar meetings.\n"
        f"• `/emails` → Review unread Gmail messages & urgent alerts.\n"
        f"• `/location <city>` → Check or update your active city/location.\n"
        f"• `/settings` → Inspect and customize dynamic preferences.\n"
        f"• `/voice_model` → Switch voice (Prabhat Indian 🇮🇳, Brian Global 🌐, Neerja Female 🇮🇳).\n"
        f"• `/status` → Inspect system diagnostics & status."
    )
    await send_safe_html_reply(update, welcome)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    user_text = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    context_data = await asyncio.to_thread(get_context_for_query, user_text)
    reply = await asyncio.to_thread(brain.ask, user_text, context_data)

    await send_safe_html_reply(update, reply)

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles Telegram location pin sharing and calibrates regional location."""
    if not is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized access.")
        return

    loc = update.message.location
    if not loc:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    loc_data = await asyncio.to_thread(brain.location_manager.update_from_coordinates, loc.latitude, loc.longitude)

    reply = (
        f"📍 <b>Location Updated Successfully</b>\n\n"
        f"• <b>City / Area:</b> {loc_data.get('city')}\n"
        f"• <b>State:</b> {loc_data.get('state')}\n"
        f"• <b>Country:</b> {loc_data.get('country')}\n\n"
        f"<i>All real-time gold rates, commodity prices, weather, and localized intelligence are now calibrated to {loc_data.get('display')}, Sir.</i>"
    )
    await send_safe_html_reply(update, reply)

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
            caption = f"🗣️ <i>\"{html.escape(transcribed_text)}\"</i>\n\n{reply}"
            html_caption = format_to_telegram_html(caption)

            with open(audio_path, "rb") as audio:
                if len(html_caption) <= 1024:
                    try:
                        await update.message.reply_voice(voice=audio, caption=html_caption, parse_mode="HTML")
                        audio_sent = True
                    except Exception:
                        await update.message.reply_voice(voice=audio, caption=caption[:1024], parse_mode=None)
                        audio_sent = True
                else:
                    short_cap = format_to_telegram_html(f"🗣️ <i>\"{html.escape(transcribed_text)}\"</i>")
                    await update.message.reply_voice(voice=audio, caption=short_cap, parse_mode="HTML")
                    await send_safe_html_reply(update, reply)
                    audio_sent = True
        except Exception as tts_err:
            logger.warning(f"TTS voice synthesis timed out or failed ({tts_err}), responding in text.")

        if not audio_sent:
            await send_safe_html_reply(update, f"🗣️ <i>\"{html.escape(transcribed_text)}\"</i>\n\n{reply}")

    except Exception as e:
        logger.error(f"[-] Error processing incoming voice/audio message: {e}", exc_info=True)
        await update.message.reply_text(f"Apologies, Sir. An error occurred processing your audio: {e}")

async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delivers an on-demand audio and text briefing."""
    if not is_authorized(update):
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    briefing_text = await scheduler.compile_briefing_text()
    try:
        audio_path = await generate_speech_file(briefing_text, filename=f"briefing_{update.message.id}.mp3")
        with open(audio_path, "rb") as audio:
            short_cap = format_to_telegram_html("🎙️ <b>Morning Executive Briefing</b>")
            await update.message.reply_voice(voice=audio, caption=short_cap, parse_mode="HTML")
            await send_safe_html_reply(update, briefing_text)
    except Exception as e:
        logger.error(f"[-] Voice synthesis failed for briefing: {e}")
        await send_safe_html_reply(update, briefing_text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays system status diagnostics."""
    if not is_authorized(update):
        return
    cal_status = "🟢 Connected (Auto-refresh enabled)" if google.is_configured() else "🔴 Disconnected"
    gemini_status = "🟢 Configured" if config.GEMINI_API_KEY else "🔴 Missing Key"
    tasks_count = len(memory.get_pending_tasks())
    loc = brain.location_manager.get_user_location()
    active_voice = memory.get_setting("voice_name", "en-IN-PrabhatNeural")

    msg = (
        f"🛡️ **{config.ASSISTANT_NAME} System Diagnostics:**\n\n"
        f"• **Cognitive Engine (Gemini)**: {gemini_status}\n"
        f"• **Location Context**: 📍 `{loc['display']}`\n"
        f"• **Live Web Search**: 🟢 Active (Real-time Gold, Weather, News)\n"
        f"• **Vocal Synthesis**: 🟢 Active (`{active_voice}`)\n"
        f"• **Continuous Learning**: 🟢 Active ({len(memory.get_learnings())} rules stored)\n"
        f"• **Google Workspace**: {cal_status}\n"
        f"• **Autonomous Scheduler**: 🟢 Active (Briefings & Guardians)\n"
        f"• **Memory Database**: 🟢 Connected ({tasks_count} pending tasks)\n"
        f"• **Primary User ID**: `{config.TELEGRAM_USER_ID or 'Not Set'}`"
    )
    await send_safe_html_reply(update, msg)

async def agenda_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not google.is_configured():
        await update.message.reply_text("⚠️ Google Calendar is not yet linked, Sir.")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    agenda = await asyncio.to_thread(google.format_daily_agenda)
    await send_safe_html_reply(update, agenda)

async def emails_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not google.is_configured():
        await update.message.reply_text("⚠️ Gmail is not yet linked, Sir.")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    emails = await asyncio.to_thread(google.get_unread_emails, 5)
    if not emails:
        await update.message.reply_text("📭 Inbox zero! You have no unread emails, Sir.")
        return
    msg = f"📬 **Recent Unread Emails ({len(emails)}):**\n\n"
    for em in emails:
        clean_subj = html.escape(em.get("subject", "No Subject"))
        clean_from = html.escape(em.get("from", "Unknown"))
        clean_snip = html.escape(em.get("snippet", "")[:120])
        msg += f"• **From:** {clean_from}\n  **Subject:** {clean_subj}\n  _{clean_snip}..._\n\n"
    await send_safe_html_reply(update, msg)

async def handle_voice_reply_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    query = " ".join(context.args) if context.args else "Report current status and readiness."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")

    context_data = await asyncio.to_thread(get_context_for_query, query)
    reply = await asyncio.to_thread(brain.ask, query, context_data)
    audio_path = await generate_speech_file(reply, filename=f"reply_{update.message.id}.mp3")

    with open(audio_path, "rb") as audio:
        short_cap = format_to_telegram_html(f"🗣️ <i>Voice Response</i>")
        await update.message.reply_voice(voice=audio, caption=short_cap, parse_mode="HTML")
        await send_safe_html_reply(update, reply)

async def location_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows checking or manually setting user location."""
    if not is_authorized(update):
        return

    arg = " ".join(context.args).strip() if context.args else ""
    if arg:
        loc_data = await asyncio.to_thread(brain.location_manager.set_manual_location, arg)
        msg = f"📍 <b>Location Updated:</b> Calibrated to <b>{loc_data.get('display')}</b>."
        await send_safe_html_reply(update, msg)
    else:
        current = brain.location_manager.get_user_location()
        msg = (
            f"📍 <b>Current Calibrated Location:</b>\n"
            f"• <b>Location:</b> <code>{current['display']}</code>\n"
            f"• <b>City:</b> {current['city']}\n"
            f"• <b>State:</b> {current['state']}\n"
            f"• <b>Country:</b> {current['country']}\n\n"
            f"<i>To change your location:</i>\n"
            f"• Send a location pin directly in this chat, or\n"
            f"• Type <code>/location &lt;City Name&gt;</code> (e.g. <code>/location Mumbai</code>), or\n"
            f"• Simply tell me: <i>\"I am in Bengaluru\"</i>."
        )
        await send_safe_html_reply(update, msg)

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    alert_msg = " ".join(context.args) if context.args else "Attention Sir: Urgent action required!"
    spoken_text = f"Sir, urgent alert: {alert_msg}"

    audio_path = await generate_speech_file(spoken_text, filename="urgent_alert.mp3")

    with open(audio_path, "rb") as audio:
        await update.message.reply_voice(
            voice=audio,
            caption=f"🚨 <b>URGENT ALARM</b> 🚨\n{html.escape(alert_msg)}",
            parse_mode="HTML"
        )

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    note_text = " ".join(context.args)
    if not note_text:
        await send_safe_html_reply(update, "Usage: <code>/note your note content here</code>")
        return
    note_id = await asyncio.to_thread(memory.add_note, note_text)
    await send_safe_html_reply(update, f"📝 <b>Note saved (ID #{note_id}):</b>\n<i>{html.escape(note_text)}</i>")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays current dynamic configuration and explains how to update settings in chat."""
    if not is_authorized(update):
        return
    settings = memory.get_all_settings()
    learnings = memory.get_learnings(10)

    u_name = settings.get("user_name", "Sir")
    a_name = settings.get("assistant_name", "Jarvis")
    b_hour = settings.get("briefing_hour", "8")
    b_min = settings.get("briefing_minute", "0").zfill(2)
    notice = settings.get("meeting_alert_minutes", "15")
    voice = settings.get("voice_name", "en-IN-PrabhatNeural")
    loc = brain.location_manager.get_user_location()

    msg = f"⚙️ **{a_name} Dynamic Configuration:**\n\n"
    msg += f"• **Your Name**: `{u_name}`\n"
    msg += f"• **Active Location**: `{loc['display']}`\n"
    msg += f"• **Active Voice Model**: `{voice}`\n"
    msg += f"• **Morning Briefing**: `{b_hour}:{b_min} IST`\n"
    msg += f"• **Meeting Notice Window**: `{notice} minutes`\n"
    msg += f"• **Timezone**: `Asia/Kolkata (IST)`\n\n"

    if learnings:
        msg += f"🧠 **Learned Rules & Preferences ({len(learnings)} active):**\n"
        for l in learnings[:4]:
            msg += f"• _{l}_\n"
        msg += "\n"

    msg += "💡 *To change any setting or add a rule, simply tell me in plain English! (e.g. 'Set briefing to 7:00 AM', 'Call me Piyush', 'I am in Mumbai', or 'From now on always...')*"
    await send_safe_html_reply(update, msg)

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    tasks = await asyncio.to_thread(memory.get_pending_tasks)
    if not tasks:
        await send_safe_html_reply(update, "✅ No pending tasks, Sir. Your slate is clean.")
        return
    msg = "📋 **Pending Tasks:**\n"
    for t in tasks:
        urgency = " 🔴 [URGENT]" if t.get("is_urgent") else ""
        due = f" (Due: {t.get('due_date')})" if t.get("due_date") else ""
        msg += f"• #{t['id']}: {t['title']}{urgency}{due}\n"
    await send_safe_html_reply(update, msg)

async def voice_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows inspecting and selecting neural voice models."""
    if not is_authorized(update):
        return
    arg = context.args[0].lower() if context.args else ""
    voice_map = {
        "prabhat": ("en-IN-PrabhatNeural", "Prabhat (Indian English Male 🇮🇳)"),
        "brian": ("en-US-BrianNeural", "Brian (Articulate Global Male 🌐)"),
        "neerja": ("en-IN-NeerjaNeural", "Neerja (Indian English Female 🇮🇳)"),
        "christopher": ("en-US-ChristopherNeural", "Christopher (Deep US Male 🇺🇸)"),
        "ryan": ("en-GB-RyanNeural", "Ryan (British Male 🇬🇧)")
    }
    if arg in voice_map:
        v_id, v_label = voice_map[arg]
        memory.set_setting("voice_name", v_id, "Selected neural voice")
        await send_safe_html_reply(update, f"🎙️ <b>Voice Model Updated:</b> Switched to <b>{v_label}</b>.")
        try:
            sample_audio = await generate_speech_file(
                f"Voice updated, Sir. I am now speaking in {v_label}.",
                filename="sample_voice.mp3",
                voice=v_id
            )
            with open(sample_audio, "rb") as audio:
                await update.message.reply_voice(voice=audio, caption=f"Sample: {v_label}")
        except Exception as e:
            logger.warning(f"Failed to send voice sample: {e}")
    else:
        current = memory.get_setting("voice_name", "en-IN-PrabhatNeural")
        msg = "🎙️ <b>Available Neural Voice Models:</b>\n\n"
        msg += "• <code>/voice_model prabhat</code> → Indian English Male 🇮🇳 (Recommended)\n"
        msg += "• <code>/voice_model brian</code> → Calm, Intelligent Global Male 🌐\n"
        msg += "• <code>/voice_model neerja</code> → Indian English Female 🇮🇳\n"
        msg += "• <code>/voice_model christopher</code> → Deep, Smooth US Male 🇺🇸\n"
        msg += "• <code>/voice_model ryan</code> → British Male 🇬🇧\n\n"
        msg += f"<b>Active Voice:</b> <code>{current}</code>\n"
        msg += "<i>Usage: <code>/voice_model brian</code> or tell me in chat 'Change voice to Brian'</i>"
        await send_safe_html_reply(update, msg)

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
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("location", location_command))
    app.add_handler(CommandHandler("voice_model", voice_model_command))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
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
