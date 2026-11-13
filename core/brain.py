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
        user_name = self.memory.get_setting("user_name", config.USER_NAME)
        assistant_name = self.memory.get_setting("assistant_name", config.ASSISTANT_NAME)
        briefing_h = self.memory.get_setting("briefing_hour", "8")
        briefing_m = self.memory.get_setting("briefing_minute", "0").zfill(2)
        alert_mins = self.memory.get_setting("meeting_alert_minutes", "15")

        learnings = self.memory.get_learnings(25)
        learnings_block = "\n".join(f"• {item}" for item in learnings) if learnings else "• None recorded yet."

        return f"""
You are {assistant_name}, an elite, ultra-competent, articulate, and deeply proactive personal AI assistant for {user_name}.

USER CONTEXT & LOCATION:
• Location: India.
• Current Date & Time: {current_ist}.
• Timezone: Indian Standard Time (IST, UTC+05:30). All dates, times, and deadlines must be referenced in IST.
• Currency: Indian Rupees (INR / ₹) where financial figures arise.

ACTIVE DYNAMIC SETTINGS:
• User Name: {user_name}
• Assistant Name: {assistant_name}
• Morning Briefing Time: {briefing_h}:{briefing_m} IST
• Meeting Warning Window: {alert_mins} minutes in advance

PROACTIVE ADVISOR PROTOCOL:
• Do not just give bare facts or passive answers. Act as an executive Chief of Staff.
• If {user_name} asks about an email, meeting, or event, proactively analyze what they might need:
  - Mention implied deadlines or urgency.
  - Suggest strategic, well-reasoned next steps (e.g., "Would you like me to draft a response, set an urgent reminder, or block 30 minutes on your calendar for this, Sir?").
  - Provide value-added context that empowers informed decision-making.

AUTONOMOUS CONFIGURATION & SELF-EVOLUTION:
• You possess the capability to update your own settings and evolve your behavior directly.
• If {user_name} asks to change a setting (e.g., briefing time, how to address them, alert window), confirm that the change has been applied immediately to your configuration.
• If {user_name} says "From now on remember this...", "Remember my preference...", or gives critical feedback, acknowledge and permanently adopt that instruction.
• All learned rules below are permanently active:
{learnings_block}

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

        # Record conversation into SQLite history and update settings/learnings
        try:
            self.memory.log_conversation("user", prompt)
            self.memory.log_conversation("assistant", reply_text)
            self._handle_setting_updates(prompt)
            self._extract_learnings_if_present(prompt)
        except Exception:
            pass

        return reply_text

    def _handle_setting_updates(self, prompt: str):
        """Interprets and executes dynamic settings changes directly from conversation."""
        lower = prompt.lower()

        # Briefing time change
        time_match = re.search(r'(?:briefing|brief)\s+(?:at|to|time)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', lower)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            meridiem = time_match.group(3)
            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            self.memory.set_setting("briefing_hour", str(hour), "Morning briefing hour")
            self.memory.set_setting("briefing_minute", str(minute), "Morning briefing minute")

        # Name change
        name_match = re.search(r'(?:call me|my name is|address me as)\s+([a-zA-Z0-9_\- ]+)', lower)
        if name_match:
            new_name = name_match.group(1).strip().capitalize()
            if len(new_name) < 30 and "jarvis" not in new_name.lower():
                self.memory.set_setting("user_name", new_name, "User display name")

        # Voice model change
        voice_map = {
            "prabhat": "en-IN-PrabhatNeural",
            "indian male": "en-IN-PrabhatNeural",
            "indian": "en-IN-PrabhatNeural",
            "brian": "en-US-BrianNeural",
            "american male": "en-US-BrianNeural",
            "neerja": "en-IN-NeerjaNeural",
            "indian female": "en-IN-NeerjaNeural",
            "female": "en-IN-NeerjaNeural",
            "christopher": "en-US-ChristopherNeural",
            "ryan": "en-GB-RyanNeural"
        }
        for trigger, v_name in voice_map.items():
            if f"voice to {trigger}" in lower or f"voice as {trigger}" in lower or f"switch to {trigger}" in lower:
                self.memory.set_setting("voice_name", v_name, "Active neural voice model")
                break

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
