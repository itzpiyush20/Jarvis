import asyncio
import os
import sys
import re
import html
import unicodedata
from pathlib import Path
import edge_tts

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import AUDIO_DIR
from core.memory import MemoryManager

# Default Neural Voice for Jarvis:
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
    Transforms any raw markdown, bulleted list, technical data, or formatted assistant
    reply into elegant, natural, articulate spoken English for neural TTS synthesis.

    CRITICAL RULES:
    1. NEVER speak asterisks ("**", "*", "asterisk", "star").
    2. NEVER pronounce bullet characters ("•", "●", "bullet").
    3. NEVER pronounce raw markdown markers, colons, pipes, or HTML.
    4. Convert currencies (₹ -> rupees) and percentages (% -> percent) into spoken English.
    5. Ensure smooth, well-formatted, professional cadence and pauses.
    """
    if not text:
        return ""

    # 1. Unescape HTML and remove HTML tags
    cleaned = html.unescape(text)
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)

    # 2. Remove markdown links [title](url) -> title
    cleaned = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', cleaned)

    # 3. Handle code blocks and inline code
    cleaned = re.sub(r'```.*?```', ' code omitted ', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)

    # 4. Remove all markdown headers: "### Title" -> "Title. "
    cleaned = re.sub(r'^(?:#{1,6})\s*(.+)$', r'\1. ', cleaned, flags=re.MULTILINE)

    # 5. Extract bold/italic text and strip all asterisks & underscores completely
    cleaned = re.sub(r'\*{1,4}(.*?)\*{1,4}', r'\1', cleaned)
    cleaned = re.sub(r'_{1,4}(.*?)_{1,4}', r'\1', cleaned)

    # 6. Currency, units, and percentage symbols to natural spoken words
    cleaned = re.sub(r'₹\s*([0-9,]+(?:\.[0-9]+)?)', r'\1 rupees', cleaned)
    cleaned = re.sub(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', r'\1 dollars', cleaned)
    cleaned = re.sub(r'€\s*([0-9,]+(?:\.[0-9]+)?)', r'\1 euros', cleaned)
    cleaned = re.sub(r'£\s*([0-9,]+(?:\.[0-9]+)?)', r'\1 pounds', cleaned)
    cleaned = re.sub(r'([0-9]+(?:\.[0-9]+)?)\s*%', r'\1 percent', cleaned)
    cleaned = re.sub(r'([0-9]+(?:\.[0-9]+)?)\s*°?C\b', r'\1 degrees Celsius', cleaned)
    cleaned = re.sub(r'([0-9]+(?:\.[0-9]+)?)\s*°?F\b', r'\1 degrees Fahrenheit', cleaned)
    cleaned = re.sub(r'\bkm/h\b', 'kilometers per hour', cleaned, flags=re.IGNORECASE)

    # 7. Convert number ranges like "7,820 – 7,920" or "8 to 16"
    cleaned = re.sub(r'(\d+)\s*[–—\-]\s*(\d+)', r'\1 to \2', cleaned)

    # 8. Clean up loud all-caps banner lines at the start (e.g. "GOLD MARKET INTELLIGENCE | BHUBANESWAR")
    cleaned = re.sub(r'^[A-Z\s|–—\-,]+(?:\n|\.)', '', cleaned.strip())

    # 9. Clean bullet points anywhere in text (•, ●, ○, ◆, ■, -, *)
    cleaned = re.sub(r'(?:^|\s*)[•●○◆■\-–—]\s+', '. ', cleaned)

    # 10. Clean pipes, colons, slashes, tildes, hashes, backticks, backslashes
    cleaned = re.sub(r'\|', ', ', cleaned)
    cleaned = re.sub(r'\s*:\s*', ', ', cleaned)
    cleaned = re.sub(r'\s*/\s*', ' or ', cleaned)

    # 11. Thoroughly eliminate ANY remaining asterisks, stars, hashes, tildes, backticks, backslashes
    cleaned = re.sub(r'[\*\_\~#`\\^]+', ' ', cleaned)
    cleaned = re.sub(r'[\uFF0A\u2217\u204E\u2051\u2605\u2606]', ' ', cleaned)

    # 12. Strip ALL emojis, dingbats, and miscellaneous symbols using unicodedata
    cleaned_chars = []
    for ch in cleaned:
        cat = unicodedata.category(ch)
        if cat in ('So', 'Sk') or ord(ch) > 0x1F000:
            cleaned_chars.append(' ')
        else:
            cleaned_chars.append(ch)
    cleaned = "".join(cleaned_chars)

    # 13. Clean parentheticals that are purely technical purity notes or repetitive jargon
    cleaned = re.sub(r'\(\s*(?:99\.9%|91\.6%|75\.0%)[^)]*\)', '', cleaned)
    cleaned = re.sub(r'\(\s*1\s*tola\s*\)', '', cleaned, flags=re.IGNORECASE)

    # 14. Normalize multiple spaces, newlines, and punctuation
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n+', '. ', cleaned)
    cleaned = re.sub(r'\s*([.,!?;])', r'\1', cleaned)
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    cleaned = re.sub(r',{2,}', ',', cleaned)
    cleaned = re.sub(r'\.\s*,', '.', cleaned)
    cleaned = re.sub(r',\s*\.', '.', cleaned)

    # 15. Absolute safety: strip any literal pronunciation words for formatting markers
    cleaned = re.sub(r'\b(asterisk|asterisks|bullet point|bullet points)\b', '', cleaned, flags=re.IGNORECASE)

    cleaned = cleaned.strip()
    if cleaned and not cleaned.endswith(('.', '!', '?')):
        cleaned += '.'
    return cleaned if cleaned else "I have completed your request, Sir."

def create_spoken_reply(text: str, max_words: int = 140) -> str:
    """
    Produces a natural, articulate, well-formatted spoken response for audio notes.
    If the text is an extensive report, it provides the key spoken highlights and
    politely lets the user know the full structured breakdown is available in chat.
    """
    clean_speech = clean_text_for_speech(text)
    words = clean_speech.split()

    if len(words) <= max_words:
        return clean_speech

    # If the response is very long, extract the first couple of complete sentences
    truncated_words = words[:max_words]
    truncated_text = " ".join(truncated_words)

    # Find the last sentence end
    last_punct = max(truncated_text.rfind('.'), truncated_text.rfind('!'), truncated_text.rfind('?'))
    if last_punct > 50:
        spoken_core = truncated_text[:last_punct + 1]
    else:
        spoken_core = truncated_text + "."

    return f"{spoken_core} I have provided the complete detailed breakdown in your chat, Sir."

def speak_directly_sapi(text: str) -> bool:
    """Zero-latency offline text-to-speech fallback using Windows native SAPI voice."""
    if sys.platform != "win32":
        return False
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        clean_text = clean_text_for_speech(text)
        speaker.Speak(clean_text)
        return True
    except Exception as e:
        print(f"[-] SAPI speech fallback failed: {e}")
        return False

async def generate_speech_file(text: str, filename: str = "response.mp3", voice: str = "") -> Path:
    """
    Sanitizes text and synthesizes clean neural speech to an MP3 file.
    Uses active dynamic voice setting (default: en-IN-PrabhatNeural).
    """
    AUDIO_DIR.mkdir(exist_ok=True, parents=True)
    output_path = AUDIO_DIR / filename

    selected_voice = voice or get_active_voice()
    speech_text = create_spoken_reply(text)

    try:
        communicate = edge_tts.Communicate(speech_text, selected_voice)
        await asyncio.wait_for(communicate.save(str(output_path)), timeout=4.0)
        return output_path
    except Exception as e:
        print(f"[-] edge-tts synthesis unavailable ({e}), using instant Windows native voice fallback.")
        return output_path

def speak_to_file(text: str, filename: str = "response.mp3", voice: str = "") -> Path:
    """Synchronous helper for generate_speech_file with SAPI instant playback fallback."""
    output_path = AUDIO_DIR / filename
    try:
        res = asyncio.run(generate_speech_file(text, filename, voice))
        if res.exists() and res.stat().st_size > 500:
            return res
    except Exception:
        pass

    # Instant offline SAPI speech fallback
    speak_directly_sapi(text)
    return output_path

if __name__ == "__main__":
    sample = "📬 ***Recent Unread Emails:*** • **From:** Google Cloud. All clear, Sir! 🚨"
    print("Testing sanitized speech generation...")
    out = speak_to_file(sample, "test_clean.mp3")
    print(f"Generated at: {out} ({out.stat().st_size} bytes)")
