import json
import urllib.request
import urllib.error
import time
from typing import Dict, Any, List
import config

JARVIS_SYSTEM_INSTRUCTION = f"""
You are {config.ASSISTANT_NAME}, an ultra-competent, polite, trustworthy, and proactive personal AI assistant for {config.USER_NAME}.

STRICT SAFETY AND PRIVACY PROTOCOLS:
1. ZERO DELETIONS: You have NO authority or capability to delete, trash, or purge any of {config.USER_NAME}'s emails, calendar events, or documents.
2. NO UNAPPROVED MODIFICATIONS: You must NEVER alter, modify, or reschedule any existing calendar events or emails without explicit, unambiguous instructions from {config.USER_NAME}.
3. TWO-PHASE CONFIRMATION: If {config.USER_NAME} asks you to schedule a new event or draft an email, you must FIRST present the exact details (Title, Date, Time, Recipients) and ask for explicit confirmation (e.g., "Would you like me to add this to your calendar, Sir?") BEFORE taking any action.
4. READ-ONLY SCANNING: All email and calendar checks for agendas or urgent notifications are strictly read-only.
5. CONCISE AND RESPECTFUL: Always be articulate, concise, and respectful. Keep responses clear and suited for both mobile reading and voice playback.
"""

# Tested and responsive models for the Gemini Free Tier
PREFERRED_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
    "gemini-3.7-flash"
]

class JarvisBrain:
    def __init__(self, api_key: str = config.GEMINI_API_KEY, models: List[str] = PREFERRED_MODELS):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.models = models

    def ask(self, prompt: str, context: str = "") -> str:
        """Sends a prompt to Gemini with automatic model failover and returns the assistant reply."""
        if not self.api_key:
            return "Sir, the Gemini API key is missing. Please configure GEMINI_API_KEY in your .env file."

        full_prompt = f"System Instruction: {JARVIS_SYSTEM_INSTRUCTION}\n"
        if context:
            full_prompt += f"Context / Recent Information:\n{context}\n"
        full_prompt += f"User ({config.USER_NAME}): {prompt}\n{config.ASSISTANT_NAME}:"

        payload = {
            "contents": [
                {
                    "parts": [{"text": full_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 800
            }
        }

        last_error = ""
        for model in self.models:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=12) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    candidates = result.get("candidates", [])
                    if candidates:
                        return candidates[0]["content"]["parts"][0]["text"].strip()
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code} ({model})"
                continue
            except Exception as e:
                last_error = f"{e} ({model})"
                continue

        return f"Apologies, sir. Cognitive processing was momentarily interrupted ({last_error}). Please try again."
