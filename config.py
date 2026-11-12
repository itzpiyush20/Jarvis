import os
import socket
from pathlib import Path

# ========================================================
# NETWORK OPTIMIZATION: Force IPv4 DNS resolution
# Bypasses the 45-second Windows TCP IPv6 timeout on Indian/home ISPs
# Reduces response times from 50s down to 1s!
# ========================================================
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_only_getaddrinfo

# Base directory
BASE_DIR = Path(__file__).resolve().parent

def load_env():
    """Loads .env file into os.environ with fallback if python-dotenv isn't installed."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except ImportError:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k not in os.environ:
                    os.environ[k] = v

load_env()

# API Keys & Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID", "")

# Assistant Persona
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Jarvis")
USER_NAME = os.getenv("USER_NAME", "Sir")

# Database Path
DB_PATH = BASE_DIR / "jarvis_memory.db"

# Audio cache folder
AUDIO_DIR = BASE_DIR / "temp_audio"
AUDIO_DIR.mkdir(exist_ok=True)
