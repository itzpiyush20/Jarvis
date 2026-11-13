import asyncio
import os
import sys
import re
import html
from pathlib import Path
import edge_tts

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import AUDIO_DIR
from core.memory import MemoryManager

# Default Neural Voice for Jarvis in Indian Context:
# "en-IN-PrabhatNeural" (Clear, professional Indian English male)
# "en-US-BrianNeural" (Articulate, natural, conversational AI male)
# "en-IN-NeerjaNeural" (Crisp, professional Indian English female)
# "en-US-ChristopherNeural" (Deep, authoritative US male)
DEFAULT_VOICE = "en-IN-PrabhatNeural"

def get_active_voice() -> str:
    """Retrieves the active voice model configured in persistent settings."""
    try:
        mem = MemoryManager()
        voice = mem.get_setting("voice_name", DEFAULT_VOICE)
        return voice or DEFAULT_VOICE
    except Exception:
        return DEFAULT_VOICE

def clean_text_for_speech(text: str) -> str:
    """
    Cleans raw markdown, emojis, asterisks, and HTML symbols from text
    so that neural voice synthesis speaks only pure, natural, fluent English.
    Eliminates all literal pronunciation of 'asterisk', 'hash', 'bullet', etc.
    """
    if not text:
        return ""

    # 1. Remove HTML tags and unescape entities
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)

    # 2. Convert markdown links [title](url) -> title
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # 3. Handle code blocks and inline code
    text = re.sub(r'```.*?```', ' code omitted ', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # 4. Remove all markdown formatting symbols (*, _, ~, #, >)
    text = re.sub(r'[*_~#>]+', ' ', text)

    # 5. Convert bullet points and list dashes into clean sentence pauses
    text = re.sub(r'^\s*[-•*]\s+', '. ', text, flags=re.MULTILINE)

    # 6. Strip emojis and pictographs so TTS doesn't describe emojis aloud
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA70-\U0001FAFF"
        "]+",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub(' ', text)

    # 7. Normalize whitespace and breath pauses
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '. ', text)
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)

    cleaned = text.strip()
    return cleaned if cleaned else "I have completed your request, Sir."

async def generate_speech_file(text: str, filename: str = "response.mp3", voice: str = "") -> Path:
    """
    Sanitizes text and synthesizes clean neural speech to an MP3 file.
    Uses active dynamic voice setting (default: en-IN-PrabhatNeural).
    """
    AUDIO_DIR.mkdir(exist_ok=True, parents=True)
    output_path = AUDIO_DIR / filename

    selected_voice = voice or get_active_voice()
    speech_text = clean_text_for_speech(text)

    communicate = edge_tts.Communicate(speech_text, selected_voice)
    await communicate.save(str(output_path))
    return output_path

def speak_to_file(text: str, filename: str = "response.mp3", voice: str = "") -> Path:
    """Synchronous helper for generate_speech_file."""
    return asyncio.run(generate_speech_file(text, filename, voice))

if __name__ == "__main__":
    sample = "📬 ***Recent Unread Emails:*** • **From:** Google Cloud. All clear, Sir! 🚨"
    print("Testing sanitized speech generation...")
    out = speak_to_file(sample, "test_clean.mp3")
    print(f"Generated at: {out} ({out.stat().st_size} bytes)")
