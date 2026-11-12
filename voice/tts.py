import asyncio
import os
from pathlib import Path
import edge_tts
from config import AUDIO_DIR

# High-quality neural voices suited for Jarvis:
# "en-GB-RyanNeural" (British accent, very much like classic Jarvis)
# "en-US-ChristopherNeural" (US authoritative/smooth)
# "en-US-GuyNeural" (friendly conversational)
DEFAULT_VOICE = "en-GB-RyanNeural"

async def generate_speech_file(text: str, filename: str = "response.mp3", voice: str = DEFAULT_VOICE) -> Path:
    """Synthesizes text to an MP3 file using Edge-TTS (Free, Neural Voice)."""
    output_path = AUDIO_DIR / filename
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))
    return output_path

def speak_to_file(text: str, filename: str = "response.mp3", voice: str = DEFAULT_VOICE) -> Path:
    """Synchronous helper for generate_speech_file."""
    return asyncio.run(generate_speech_file(text, filename, voice))
