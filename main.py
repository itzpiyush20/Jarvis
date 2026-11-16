import argparse
import asyncio
import sys
import os
import threading
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from core.brain import JarvisBrain
from core.memory import MemoryManager
from integrations.google_services import GoogleServices
from core.scheduler import JarvisScheduler
from integrations.telegram_bot import start_telegram_service
from voice.listener import DesktopVoiceAssistant, start_voice_service

BANNER = r"""
   ╦╔═╗╦═╗╦  ╦╦╔═╗
   ║╠═╣╠╦╝╚╗╔╝║╚═╗
  ╚╝╩ ╩╩╚═ ╚╝ ╩╚═╝
 Personal AI Assistant 🎙️
"""

def print_banner():
    print(BANNER)
    print("=" * 60)
    print(f" Assistant: {config.ASSISTANT_NAME} | User: {config.USER_NAME}")
    print("=" * 60)

def run_diagnostics():
    print_banner()
    print("[*] Running System Diagnostics...\n")

    # 1. Config & Gemini
    brain = JarvisBrain()
    gemini_ok = bool(config.GEMINI_API_KEY)
    print(f" [•] Gemini Brain API Key : {'🟢 OK' if gemini_ok else '🔴 Missing (GEMINI_API_KEY)'}")

    # 2. Desktop Wake-Word & Audio Hardware
    try:
        import sounddevice as sd
        in_dev = sd.query_devices(kind="input")
        out_dev = sd.query_devices(kind="output")
        print(f" [•] Default Microphone   : 🟢 {in_dev['name']}")
        print(f" [•] Default Speakers     : 🟢 {out_dev['name']}")
    except Exception as e:
        print(f" [•] Audio Devices Check  : ⚠️ Error ({e})")

    try:
        from openwakeword.model import Model
        oww = Model(wakeword_models=[config.WAKE_WORD_MODEL], inference_framework="onnx")
        print(f" [•] Wake-Word Engine     : 🟢 Ready ('{config.WAKE_WORD_MODEL}')")
    except Exception as e:
        print(f" [•] Wake-Word Engine     : 🔴 Model missing or error ({e})")

    # 3. Telegram Bot
    tg_token_ok = bool(config.TELEGRAM_BOT_TOKEN)
    print(f" [•] Telegram Bot Token   : {'🟢 OK' if tg_token_ok else '⚪ Not configured (Optional for Desktop Voice)'}")
    print(f" [•] Primary Telegram User: {config.TELEGRAM_USER_ID or '⚠️ None (Will pair on /start)'}")

    # 4. Google Workspace
    gs = GoogleServices()
    google_ok = gs.is_configured()
    print(f" [•] Google Workspace     : {'🟢 Linked (token.json)' if google_ok else '⚪ Not configured (credentials.json needed)'}")

    # 5. Memory
    mem = MemoryManager()
    tasks = mem.get_pending_tasks()
    print(f" [•] SQLite Memory Engine : 🟢 Active ({len(tasks)} pending tasks)")

    # 6. Audio Cache
    audio_dir = config.AUDIO_DIR
    print(f" [•] Voice Cache Directory: 🟢 Ready ({audio_dir})")
    print("\n" + "=" * 60 + "\n")

async def run_cli_briefing():
    print_banner()
    print("[*] Compiling Daily Briefing...\n")
    scheduler = JarvisScheduler()
    briefing = await scheduler.compile_briefing_text()
    print(briefing)
    print("\n" + "=" * 60 + "\n")

def run_all_services():
    """Runs both Telegram Bot and Desktop Voice Assistant concurrently."""
    print_banner()
    print("[*] Launching Jarvis in Unified Dual Mode (Desktop Voice + Telegram Bot)...")

    # Start Desktop Voice Assistant in a background daemon thread
    assistant = DesktopVoiceAssistant()
    voice_thread = threading.Thread(target=assistant.listen_loop, daemon=True, name="JarvisVoiceListener")
    voice_thread.start()

    # Run Telegram Bot in the foreground
    try:
        start_telegram_service()
    except KeyboardInterrupt:
        print("\n[*] Shutting down Jarvis Unified Services. Have a wonderful day, Sir.")
        assistant.stop()

def main():
    parser = argparse.ArgumentParser(description="Jarvis Personal AI Assistant")
    parser.add_argument("--status", action="store_true", help="Run system diagnostics and exit")
    parser.add_argument("--briefing", action="store_true", help="Output current daily briefing and exit")
    parser.add_argument("--voice", action="store_true", help="Run desktop hands-free voice listener only")
    parser.add_argument("--telegram", action="store_true", help="Run Telegram companion bot only")
    parser.add_argument("--all", action="store_true", help="Run both Telegram bot and desktop voice listener")
    args = parser.parse_args()

    if args.status:
        run_diagnostics()
        return

    if args.briefing:
        asyncio.run(run_cli_briefing())
        return

    if args.voice:
        print_banner()
        start_voice_service()
        return

    if args.telegram:
        print_banner()
        if not config.TELEGRAM_BOT_TOKEN:
            print("[!] TELEGRAM_BOT_TOKEN is not configured in .env.")
            sys.exit(1)
        start_telegram_service()
        return

    if args.all:
        run_all_services()
        return

    # Default launch logic:
    # If both Telegram token and wake word are enabled, launch unified mode.
    # If no Telegram token, start desktop voice directly.
    if config.ENABLE_WAKE_WORD and config.TELEGRAM_BOT_TOKEN:
        run_all_services()
    elif config.ENABLE_WAKE_WORD:
        print_banner()
        print("[*] Telegram token not detected. Starting Desktop Voice Assistant...")
        start_voice_service()
    else:
        print_banner()
        start_telegram_service()

if __name__ == "__main__":
    main()
