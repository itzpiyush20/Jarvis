import json
import base64
import datetime
import urllib.request
import urllib.error
import time
import re
from typing import Dict, Any, List, Optional
import config
from core.memory import MemoryManager

# Tested and responsive models for the Gemini Free Tier
PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

class JarvisBrain:
    def __init__(self, api_key: str = config.GEMINI_API_KEY, models: List[str] = PREFERRED_MODELS):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.models = models
        self.memory = MemoryManager()

    def _get_current_ist_string(self) -> str:
        """Returns current date and time formatted in Indian Standard Time (IST)."""
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now_ist = datetime.datetime.now(ist_tz)
        return now_ist.strftime("%A, %d %B %Y at %I:%M %p IST")

    def _build_system_instruction(self) -> str:
        current_ist = self._get_current_ist_string()
        learnings = self.memory.get_learnings(20)
        learnings_block = "\n".join(f"• {item}" for item in learnings) if learnings else "• None recorded yet."

        return f"""
You are {config.ASSISTANT_NAME}, an elite, ultra-competent, articulate, and deeply proactive personal AI assistant for {config.USER_NAME}.

USER CONTEXT & LOCATION:
• Location: India.
• Current Date & Time: {current_ist}.
• Timezone: Indian Standard Time (IST, UTC+05:30). All dates, times, and deadlines must be referenced in IST.
• Currency: Indian Rupees (INR / ₹) where financial figures arise.

PROACTIVE ADVISOR PROTOCOL:
• Do not just give bare facts or passive answers. Act as an executive Chief of Staff.
• If {config.USER_NAME} asks about an email, meeting, or event, proactively analyze what they might need:
  - Mention implied deadlines or urgency.
  - Suggest strategic, well-reasoned next steps (e.g., "Would you like me to draft a response, set an urgent reminder, or block 30 minutes on your calendar for this, Sir?").
  - Provide value-added context that empowers informed decision-making.

CONTINUOUS LEARNING & PERSONALIZATION:
• You must strictly adhere to the user's learned preferences and habits:
{learnings_block}
• If {config.USER_NAME} specifies a preference, correction, or personal habit, adopt it immediately.

FORMATTING & TYPOGRAPHY:
• Format responses cleanly for mobile Telegram reading.
• Use structured sections, clean bullet points (•), and tasteful emojis.
• Avoid excessive or raw multi-asterisk markers.

STRICT SAFETY AND PRIVACY PROTOCOLS:
1. ZERO DELETIONS: You have NO authority or capability to delete, trash, or purge any emails, calendar events, or documents.
2. NO UNAPPROVED MODIFICATIONS: You must NEVER alter, modify, or reschedule any existing calendar events or emails without explicit instruction.
3. TWO-PHASE CONFIRMATION: If scheduling an event or drafting an email, FIRST present exact details and ask for explicit confirmation before taking action.
4. READ-ONLY SCANNING: All email and calendar checks for agendas or urgent notifications are strictly read-only.
"""

    def ask(self, prompt: str, context: str = "") -> str:
        """Sends a prompt to Gemini with Indian context, learned memory, multi-turn history, and proactive insights."""
        if not self.api_key:
            return "Sir, the Gemini API key is missing. Please configure GEMINI_API_KEY in your .env file."

        system_instruction = self._build_system_instruction()
        recent_history = self.memory.get_recent_history(limit=6)

        full_prompt = f"System Instruction:\n{system_instruction}\n\n"

        if recent_history:
            full_prompt += "Recent Conversation Context:\n"
            for turn in recent_history:
                speaker = config.USER_NAME if turn["role"] == "user" else config.ASSISTANT_NAME
                full_prompt += f"{speaker}: {turn['message']}\n"
            full_prompt += "\n"

        if context:
            full_prompt += f"Live Real-Time Data (Calendar / Emails / Tasks):\n{context}\n\n"

        full_prompt += f"Current Input ({config.USER_NAME}): {prompt}\n{config.ASSISTANT_NAME}:"

        payload = {
            "contents": [
                {
                    "parts": [{"text": full_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.6,
                "maxOutputTokens": 900
            }
        }

        last_error = ""
        reply_text = ""
        for model in self.models:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=14) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    candidates = result.get("candidates", [])
                    if candidates:
                        reply_text = candidates[0]["content"]["parts"][0]["text"].strip()
                        break
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code} ({model})"
                continue
            except Exception as e:
                last_error = f"{e} ({model})"
                continue

        if not reply_text:
            reply_text = f"Apologies, Sir. Cognitive processing was momentarily interrupted ({last_error}). Please try again."

        # Record conversation into SQLite history
        try:
            self.memory.log_conversation("user", prompt)
            self.memory.log_conversation("assistant", reply_text)
            self._extract_learnings_if_present(prompt)
        except Exception:
            pass

        return reply_text

    def _extract_learnings_if_present(self, user_prompt: str):
        """Detects if user shared a preference or correction and saves it to continuous learning memory."""
        lower = user_prompt.lower()
        triggers = [
            "i prefer", "always ", "remember that", "from now on", "my name is",
            "i am in", "i live in", "my work", "don't call me", "i like ", "never "
        ]
        if any(t in lower for t in triggers):
            # Fast extraction via prompt
            extract_prompt = (
                f"Identify if the user is stating a personal preference, fact, habit, or correction in this message: "
                f"\"{user_prompt}\". If yes, summarize it into ONE concise declarative rule (e.g., 'User prefers concise summaries'). "
                f"If no relevant preference is stated, reply 'NONE'."
            )
            payload = {
                "contents": [{"parts": [{"text": extract_prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 60}
            }
            try:
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
                req = urllib.request.Request(
                    endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    cand = data.get("candidates", [])
                    if cand:
                        rule = cand[0]["content"]["parts"][0]["text"].strip()
                        if rule and "NONE" not in rule.upper() and len(rule) < 150:
                            self.memory.add_learning(rule, category="preference")
            except Exception:
                pass

    def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        """Transcribes audio speech to text using Gemini's native audio capabilities."""
        if not self.api_key or not audio_bytes:
            return ""

        encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": encoded_audio
                            }
                        },
                        {
                            "text": "Transcribe the spoken words in this voice note accurately. Return ONLY the transcribed text without quotes, markdown headers, or explanations."
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 400
            }
        }

        for model in self.models:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=25) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    candidates = result.get("candidates", [])
                    if candidates:
                        return candidates[0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                print(f"[-] Transcribe attempt with {model} failed: {e}")
                continue

        return ""
