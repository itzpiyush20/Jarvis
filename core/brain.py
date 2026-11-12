import json
import urllib.request
import urllib.error
import time
from typing import Dict, Any, List
import config

JARVIS_SYSTEM_INSTRUCTION = f"""
You are {config.ASSISTANT_NAME}, an ultra-competent, polite, witty, and proactive personal AI assistant for {config.USER_NAME}.
You help manage tasks, schedule calendar events, prioritize emails, and deliver concise, natural spoken responses.
Always be concise, articulate, and respectful. Address the user naturally as {config.USER_NAME} when appropriate.
Keep answers brief and suited for voice playback unless {config.USER_NAME} asks for detailed elaboration.
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
                err_msg = e.read().decode("utf-8")
                last_error = f"HTTP {e.code} ({model})"
                # On 503 or 404, fall through to next model
                continue
            except Exception as e:
                last_error = f"{e} ({model})"
                continue

        return f"Apologies, sir. Cognitive processing was momentarily interrupted ({last_error}). Please try again."
