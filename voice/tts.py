import asyncio
import os
import sys
from pathlib import Path
import edge_tts

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import AUDIO_DIR

# High-quality neural voices suited for Jarvis:
# "en-GB-RyanNeural" (British accent, very much like classic Jarvis)
# "en-US-ChristopherNeural" (US authoritative/smooth)
# "en-US-GuyNeural" (friendly conversational)
DEFAULT_VOICE = "en-GB-RyanNeural"

async def generate_speech_file(text: str, filename: str = "response.mp3", voice: str = DEFAULT_VOICE) -> Path:
    """Synthesizes text to an MP3 file using Edge-TTS (Free, Neural Voice)."""
    AUDIO_DIR.mkdir(exist_ok=True, parents=True)
    output_path = AUDIO_DIR / filename
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))
    return output_path

def speak_to_file(text: str, filename: str = "response.mp3", voice: str = DEFAULT_VOICE) -> Path:
    """Synchronous helper for generate_speech_file."""
    return asyncio.run(generate_speech_file(text, filename, voice))

if __name__ == "__main__":
    print("[*] Generating test audio with Jarvis voice...")
    out = speak_to_file("Hello Sir, voice protocols are now online and functioning perfectly.", "test_voice.mp3")
    print(f"[+] Audio generated successfully at: {out} ({out.stat().st_size} bytes)")
