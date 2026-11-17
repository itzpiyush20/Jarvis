import os
import sys
import socket
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Ensure stdout/stderr exist in windowless execution (pythonw.exe on Windows)
if sys.stdout is None:
    try:
        (BASE_DIR / "temp_audio").mkdir(exist_ok=True)
        sys.stdout = open(BASE_DIR / "temp_audio" / "jarvis_voice.log", "a", encoding="utf-8")
    except Exception:
        sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    try:
        (BASE_DIR / "temp_audio").mkdir(exist_ok=True)
        sys.stderr = open(BASE_DIR / "temp_audio" / "jarvis_voice.log", "a", encoding="utf-8")
    except Exception:
        sys.stderr = open(os.devnull, "w")

# System socket uses standard dual-stack (IPv4/IPv6 Happy Eyeballs) resolution

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

# Cloud Environment Detection (Render, Railway, Fly, Heroku, etc.)
IS_CLOUD_DEPLOYMENT = bool(
    os.getenv("RENDER") or
    os.getenv("RAILWAY_ENVIRONMENT") or
    os.getenv("DYNO") or
    os.getenv("FLY_APP_NAME") or
    os.getenv("K_SERVICE")
)

# Wake-Word / Desktop Voice Configuration
# Automatically disabled in headless cloud environments where no physical microphone exists
_default_wake = "false" if IS_CLOUD_DEPLOYMENT else "true"
ENABLE_WAKE_WORD = os.getenv("ENABLE_WAKE_WORD", _default_wake).lower() in ("true", "1", "yes")
WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL", "hey_jarvis_v0.1.onnx")
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.1"))
MIC_DEVICE_INDEX = int(os.getenv("MIC_DEVICE_INDEX")) if os.getenv("MIC_DEVICE_INDEX", "").strip().isdigit() else None

# Software microphone gain multiplier — amplifies quiet laptop mics before
# wake-word processing. Set higher (e.g. 10-30) if your mic is very quiet.
# "auto" will calibrate during startup.
_mic_gain_raw = os.getenv("MIC_GAIN", "auto")
MIC_GAIN = _mic_gain_raw if _mic_gain_raw.lower() == "auto" else float(_mic_gain_raw)
