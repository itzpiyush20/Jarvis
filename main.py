import argparse
import asyncio
import sys
import os
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

BANNER = r"""
   ╦╔═╗╦═╗╦  ╦╦╔═╗
   ║╠═╣╠╦╝╚╗╔╝║╚═╗
  ╚╝╩ ╩╩╚═ ╚╝ ╩╚═╝
 Personal AI Assistant
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

    # 2. Telegram Bot
    tg_token_ok = bool(config.TELEGRAM_BOT_TOKEN)
    print(f" [•] Telegram Bot Token   : {'🟢 OK' if tg_token_ok else '🔴 Missing (TELEGRAM_BOT_TOKEN)'}")
    print(f" [•] Primary Telegram User: {config.TELEGRAM_USER_ID or '⚠️ None (Will pair on /start)'}")

    # 3. Google Workspace
    gs = GoogleServices()
    google_ok = gs.is_configured()
    print(f" [•] Google Workspace     : {'🟢 Linked (token.json)' if google_ok else '⚪ Not configured (credentials.json needed)'}")

    # 4. Memory
    mem = MemoryManager()
    tasks = mem.get_pending_tasks()
    print(f" [•] SQLite Memory Engine : 🟢 Active ({len(tasks)} pending tasks)")

    # 5. Audio Directory
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

def main():
    parser = argparse.ArgumentParser(description="Jarvis Personal AI Assistant")
    parser.add_argument("--status", action="store_true", help="Run system diagnostics and exit")
    parser.add_argument("--briefing", action="store_true", help="Output current daily briefing and exit")
    args = parser.parse_args()

    if args.status:
        run_diagnostics()
        return

    if args.briefing:
        asyncio.run(run_cli_briefing())
        return

    print_banner()
    run_diagnostics()

    if not config.TELEGRAM_BOT_TOKEN:
        print("[!] TELEGRAM_BOT_TOKEN is not set in .env.")
        print("    Please set TELEGRAM_BOT_TOKEN and try again.")
        sys.exit(1)

    try:
        start_telegram_service()
    except KeyboardInterrupt:
        print("\n[*] Jarvis shutting down gracefully. Have a pleasant day, Sir.")

if __name__ == "__main__":
    main()
