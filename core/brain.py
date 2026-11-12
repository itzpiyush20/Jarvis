import json
import urllib.request
import urllib.error
from typing import Dict, Any, List
import config

JARVIS_SYSTEM_INSTRUCTION = f"""
You are {config.ASSISTANT_NAME}, an ultra-competent, polite, witty, and proactive personal AI assistant for {config.USER_NAME}.
You help manage tasks, schedule calendar events, prioritize emails, and deliver concise, natural spoken responses.
Always be concise, articulate, and respectful. Address the user naturally as {config.USER_NAME} when appropriate.
Keep answers brief and suited for voice playback unless {config.USER_NAME} asks for detailed elaboration.
"""

class JarvisBrain:
    def __init__(self, api_key: str = config.GEMINI_API_KEY, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model = model
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def ask(self, prompt: str, context: str = "") -> str:
        """Sends a prompt to Gemini and returns the assistant's reply."""
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

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if candidates:
                    return candidates[0]["content"]["parts"][0]["text"].strip()
                return "I received an empty response from the core, sir."
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8")
            return f"Network error during cognitive processing: HTTP {e.code}. Details: {err}"
        except Exception as e:
            return f"An unexpected error occurred, sir: {str(e)}"
