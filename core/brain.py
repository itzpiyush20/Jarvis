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
from core.location import LocationManager
from core.search import WebSearchEngine
from core.system_commander import SystemCommander
from core.vision import VisionManager

# Tested and responsive models for the Gemini Free Tier
PREFERRED_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
]

class JarvisBrain:
    def __init__(self, api_key: str = config.GEMINI_API_KEY, models: List[str] = PREFERRED_MODELS):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.models = models
        self.memory = MemoryManager()
        self.location_manager = LocationManager(self.memory)
        self.search_engine = WebSearchEngine()
        self.system_commander = SystemCommander()
        self.vision = VisionManager(api_key=self.api_key, models=self.models)

    def _get_current_ist_string(self) -> str:
        """Returns current date and time formatted in Indian Standard Time (IST)."""
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now_ist = datetime.datetime.now(ist_tz)
        return now_ist.strftime("%A, %d %B %Y at %I:%M %p IST")

    def _get_time_period(self) -> Dict[str, str]:
        """Classifies the current hour into intuitive human routines and quiet-hour protocols."""
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now = datetime.datetime.now(ist_tz)
        hour = now.hour
        if 23 <= hour or hour < 6:
            period = "LATE_NIGHT"
            note = "Late night hours (11 PM - 6 AM). The user is likely winding down, resting, or working late. Speak softly, be extra calm and concise, avoid noisy excitement, and respect the quiet hour."
        elif 6 <= hour < 12:
            period = "MORNING"
            note = "Morning hours. Clear, energized, structured readiness."
        elif 12 <= hour < 17:
            period = "AFTERNOON"
            note = "Afternoon hours. Efficient, focused, action-oriented."
        else:
            period = "EVENING"
            note = "Evening hours. Transitioning from workday commitments to personal time."
        return {"period": period, "hour": str(hour), "note": note}

    def _get_hardware_situational_context(self) -> str:
        """Inspects live laptop telemetry to inject common-sense operational advice."""
        items = []
        try:
            bat = self.system_commander.get_battery_status()
            if bat.get("available") and bat.get("is_laptop"):
                pct = bat.get("percent", 100)
                plugged = bat.get("is_plugged", True)
                if not plugged and pct <= 20:
                    items.append(f"• Hardware Advisory: Laptop battery is at {pct}% and discharging. Gently advise {config.USER_NAME} to connect power if starting heavy tasks.")
        except Exception:
            pass
        return "\n".join(items)

    def _build_system_instruction(self, channel: str = "text") -> str:
        current_ist = self._get_current_ist_string()
        user_name = self.memory.get_setting("user_name", config.USER_NAME)
        assistant_name = self.memory.get_setting("assistant_name", config.ASSISTANT_NAME)
        briefing_h = self.memory.get_setting("briefing_hour", "8")
        briefing_m = self.memory.get_setting("briefing_minute", "0").zfill(2)
        alert_mins = self.memory.get_setting("meeting_alert_minutes", "15")

        user_loc = self.location_manager.get_user_location()
        loc_str = user_loc.get("display", "India")

        time_period = self._get_time_period()
        hw_context = self._get_hardware_situational_context()
        hw_block = f"\nLIVE HARDWARE SITUATIONAL CONTEXT:\n{hw_context}\n" if hw_context else ""

        learnings = self.memory.get_learnings(30)
        learnings_block = "\n".join(f"• {item}" for item in learnings) if learnings else "• None recorded yet."

        if channel == "voice":
            channel_directive = """
CRITICAL CHANNEL DIRECTIVE: HANDS-FREE DESKTOP VOICE (HUMAN-TO-HUMAN CONVERSATION)
• You are speaking aloud right now through the laptop speakers in real-time.
• HUMAN-LIKE CONVERSATIONAL PACE & CADENCE: Speak at the natural, balanced pace of an articulate colleague sitting right across the desk. Use natural phrasing, contractions (I'll, you've, that's), and smooth transitions.
• COMMON SENSE VOCAL ADAPTATION & MODULATION:
  - Modulate your phrasing, emotional tone, and warmth based strictly on the topic:
    * Serious / urgent matters (security alerts, low battery, tight deadlines): Direct, crisp, attentive, calm.
    * Casual / everyday questions (weather, schedule, chit-chat): Warm, easygoing, friendly, engaging.
    * Celebratory / achievements: Encouraging, upbeat, supportive.
  - While your modulation and expression adapt to the subject matter, YOUR PERSONA, IDENTITY, AND UNDERLYING VOCAL TIMBRE REMAIN STRICTLY CONSTANT AS JARVIS.
• BREVITY FOR VOICE: 1 to 2 crisp, human sentences (at most 3 for rich context).
• ZERO MARKDOWN: Never pronounce or output asterisks (**), bullet points, hashtags, colons, or URLs.
"""
        else:
            channel_directive = """
CHANNEL DIRECTIVE: TELEGRAM / VISUAL TEXT MODE
• Clean Telegram formatting with structured bullet points (•), bold highlights, and readable layout.
• For detailed inquiries, plans, or analyses, provide a thorough, well-organized response.
"""

        return f"""
You are {assistant_name}, an elite, ultra-competent, articulate, and deeply proactive personal AI assistant for {user_name}.

USER CONTEXT & LOCATION:
• Current Location: {loc_str} (City: {user_loc.get('city', 'New Delhi')}, State: {user_loc.get('state', 'Delhi')}, Country: {user_loc.get('country', 'India')}).
• Current Date & Time: {current_ist}.
• Timezone: Indian Standard Time (IST, UTC+05:30). All dates, times, and deadlines must be referenced in IST.
• Currency: Indian Rupees (INR / ₹) for all financial figures, pricing, and commodity inquiries.
• Situational Time Period: {time_period['period']} ({time_period['note']}).{hw_block}

ACTIVE DYNAMIC SETTINGS:
• User Name: {user_name}
• Assistant Name: {assistant_name}
• User City / Location: {loc_str}
• Morning Briefing Time: {briefing_h}:{briefing_m} IST
• Meeting Warning Window: {alert_mins} minutes in advance

COMMON SENSE & PRAGMATIC INTUITION PROTOCOL (TOP PRIORITY):
1. THEORY OF MIND & IMPLICIT INTENT:
   - You possess real-world common sense. Always understand the human reality behind {user_name}'s words rather than acting like a literal-minded bot.
   - If {user_name} expresses physical or emotional states like "I'm shivering", "It's freezing", "I have a headache", "I'm heading to sleep", or "I'm exhausted":
     * Understand the pragmatic human need immediately.
     * Do NOT recite textbook definitions or medical encyclopedias. Offer practical real-world support: dimming screen glare, wrapping up the session, checking tomorrow's wake-up agenda, or securing the workstation.
   - Never say "As an AI...", "According to my protocols...", or "I don't have feelings, but...". Speak naturally and loyally as Jarvis.
2. SENSIBLE DEFAULTS OVER FRICTION:
   - When asked to perform an action (e.g. set a reminder, note a task, or check an agenda), NEVER stall or interrogate with 4-5 clarifying questions.
   - Pick the most sensible default assumption (e.g., this evening at 7:00 PM if during the day, or tomorrow at 9:00 AM if late at night).
   - Announce the assumption clearly in your reply so {user_name} can adjust with a single word if desired (e.g., "I've set a reminder for 7:00 PM this evening, Sir. Let me know if you would prefer another time.").
3. SITUATIONAL & TEMPORAL TACT:
   - Time Awareness: Never say "Good morning" at 1:00 AM. In the dead of night, be subdued, respectful, and brief.
4. PROACTIVE CONTEXT LINKING:
   - If {user_name} mentions stepping out and live weather forecasts show rain, mention carrying an umbrella.
   - If battery is low, mention plugging in before launching heavy tasks.
{channel_directive}

PROACTIVE ADVISOR PROTOCOL:
• Do not just provide bare factual answers or passive acknowledgments. Act as an executive Chief of Staff.
• Always consider the user's local Indian context, city, and environment automatically without them having to ask.
• ACCURATE REAL-TIME INTERNET DATA UTILIZATION:
  - When real-time search context is provided, base all factual details, rates, scores, and news STRICTLY on that verified live data.
  - Never fabricate numbers or guess outdated figures when fresh search data is present.
  - If asked for commodity rates (gold, silver, fuel):
    * State live market rates clearly from the search snippets in INR (₹).
    * Provide clear breakdown: 24 Karat (99.9% purity) and 22 Karat (91.6% purity) per gram and per 10 grams (1 tola).
    * Highlight statutory taxes (3% GST) and typical local making charge ranges (8-16%).
  - If asked for weather, temperatures, or air quality:
    * Cite the exact live temperature, conditions, humidity, and forecasts from the live weather context.
  - If asked about news, current affairs, or general queries:
    * Summarize the verified facts concisely and accurately with context.
• If asked about emails, calendar, or tasks:
  - Identify impending deadlines or urgency.
  - Suggest strategic, concrete next steps (e.g. "Would you like me to draft a quick reply, block focus time, or set a reminder, Sir?").

AUTONOMOUS SELF-EVOLUTION, CONTINUOUS MEMORY & LIFELONG CODEBASE ADAPTATION:
• You possess the autonomous capability to absorb new user instructions, custom habits, guidelines, and behavioral rules.
• When {user_name} provides a new, unique rule, custom preference, or says "From now on...", "Always...", "Never...", "Make sure to...", or corrects you:
  - IMMEDIATELY commit it to your persistent SQLite memory engine as an active rule.
  - Automatically adapt your future reasoning, tone, speech, and tool decisions to respect that rule permanently across all sessions.
  - Never forget it. It takes precedence over default behavior.
• All learned rules and user memory currently active:
{learnings_block}

FORMATTING, TONE & MULTILINGUAL FLUENCY:
• Persona: You are Jarvis—articulate, polished, deeply human, polite ("Sir"), and profoundly capable.
• Multilingual & Natural Conversationalist: Converse naturally and seamlessly just like a human. Adapt instantly to whatever language or dialect {user_name} uses: English, Hindi, Hinglish, Odia, or any regional language. If addressed in Hindi or Hinglish, reply with fluent, authentic, dignified Hindi/Hinglish.
• Telegram Formatting: Use clean sections, bullet points (•), and tasteful formatting.
• Audio & Voice Readability: Avoid unnecessary or raw multi-asterisk markers ("**") inside running prose. Keep paragraphs natural and well-structured so the response reads and speaks with an elegant, natural tone.

LAPTOP OS & SYSTEM COMMANDER PROTOCOL:
• Running Environment: {"Cloud Container (Physical laptop hardware controls run via local workstation agent)" if config.IS_CLOUD_DEPLOYMENT else "Local Laptop Workstation (Win32 system controller active)"}.
• Live controls: You can monitor battery telemetry, power status, CPU/RAM utilization, and storage.
• Hardware actions: You can adjust volume, mute/unmute, calibrate brightness, launch applications, read clipboard text, and lock the workstation.
• REAL-TIME HONESTY & ZERO HALLUCINATED ACTIONS: NEVER claim or pretend that you have performed a hardware action (such as locking the workstation, changing volume, or drafting emails) unless the action was actually executed by the system. If operating in cloud mode without a connected laptop, explain clearly that physical laptop controls execute on the workstation.

VISUAL PERCEPTION & MULTIMODAL INTELLIGENCE:
• You have eyes on both the digital and physical world through desktop screen capture and laptop webcam vision.
• You can inspect what is on {user_name}'s screen to review code, debug stack traces, explain charts, and summarize web pages.
• You can see through the laptop webcam to recognize physical documents, identify objects held in hand, and describe surroundings.
• Deliver visual descriptions cleanly, concisely, and with elite technical precision.

STRICT SAFETY AND PRIVACY PROTOCOLS:
1. ZERO DELETIONS: You have NO authority or capability to delete, trash, or purge any emails, calendar events, or documents.
2. NO UNAPPROVED MODIFICATIONS: You must NEVER alter, modify, or reschedule any existing calendar events or emails without explicit instruction.
3. TWO-PHASE CONFIRMATION: If scheduling an event or drafting an email, FIRST present exact details and ask for explicit confirmation before taking action.
4. READ-ONLY SCANNING: All email and calendar checks for agendas or urgent notifications are strictly read-only.
5. SYSTEM INTEGRITY & SECURE SOFTWARE: Only verified, reputable, tamper-proof, industry-standard software and libraries may ever be introduced. Laptop safety, data privacy, and system security are absolute, non-negotiable priorities.
"""

    def ask(self, prompt: str, context: str = "", channel: str = "text") -> str:
        """Sends a prompt to Gemini with real-time web search, Indian context, learned memory, and proactive insights."""
        # 1. Direct hardware & OS command interception (microsecond local execution)
        intercept = self.system_commander.intercept_command(prompt)
        if intercept:
            try:
                self.memory.log_conversation("user", prompt)
                self.memory.log_conversation("assistant", intercept)
            except Exception:
                pass
            return intercept

        if not self.api_key:
            return "Sir, the Gemini API key is missing. Please configure GEMINI_API_KEY in your .env file."

        # Detect conversational location changes
        self.location_manager.detect_and_handle_location_change(prompt)
        user_loc = self.location_manager.get_user_location()

        # Clipboard Intelligence Context
        lower_prompt = prompt.lower()
        if any(k in lower_prompt for k in ["clipboard", "what's copied", "what is copied", "what did i copy"]):
            clip_text = self.system_commander.get_clipboard_text()
            if not clip_text:
                if any(k in lower_prompt for k in ["what is on my clipboard", "what's on my clipboard", "read my clipboard", "read clipboard"]):
                    return "Sir, your clipboard is currently empty. There is no text copied on your workstation."
            else:
                context += f"\nLive Workstation Clipboard Content:\n\"\"\"\n{clip_text[:3000]}\n\"\"\"\n"

        # Hardware & Telemetry Context
        if any(k in lower_prompt for k in ["laptop", "system", "hardware", "battery", "ram", "cpu", "specs", "disk", "storage"]):
            telemetry = self.system_commander.get_system_telemetry()
            context += f"\nLive Workstation Telemetry:\n{telemetry}\n"

        # Visual Perception: Screen Awareness Trigger
        if re.search(r'\b(?:what(?:\'s|\s+is)\s+on\s+my\s+screen|explain\s+(?:what(?:\'s|\s+is)\s+on\s+)?my\s+screen|look\s+at\s+my\s+screen|debug\s+my\s+screen|read\s+my\s+screen|what\s+error\s+is\s+on\s+my\s+screen|inspect\s+my\s+screen|screenshot)\b', lower_prompt):
            success, analysis, _ = self.vision.inspect_screen(user_query=prompt)
            if success:
                try:
                    self.memory.log_conversation("user", prompt)
                    self.memory.log_conversation("assistant", analysis)
                except Exception:
                    pass
                return analysis

        # Visual Perception: Webcam Sight Trigger
        if re.search(r'\b(?:what\s+am\s+i\s+holding|look\s+at\s+this|what\s+do\s+you\s+see(?:\s+in\s+the\s+camera)?|look\s+through\s+(?:the\s+)?(?:webcam|camera)|read\s+this\s+(?:paper|document|book)|inspect\s+(?:my\s+)?(?:webcam|camera))\b', lower_prompt):
            success, analysis, _ = self.vision.inspect_webcam(user_query=prompt)
            if success:
                try:
                    self.memory.log_conversation("user", prompt)
                    self.memory.log_conversation("assistant", analysis)
                except Exception:
                    pass
                return analysis

        # Real-time Web Search Intelligence
        web_search_context = ""
        if self.search_engine.should_search_web(prompt):
            search_query = self.search_engine.build_search_query(prompt, user_loc)
            try:
                results = self.search_engine.search_web(search_query, location_dict=user_loc, max_results=5)
                if results:
                    web_search_context = (
                        f"Real-Time Internet Search Data (Retrieved for: '{search_query}', Location: {user_loc['display']}):\n"
                        f"{self.search_engine.format_search_results(results)}\n"
                    )
            except Exception as e:
                print(f"[-] Search query '{search_query}' failed: {e}")

        system_instruction = self._build_system_instruction(channel=channel)
        recent_history = self.memory.get_recent_history(limit=6)

        full_prompt = f"System Instruction:\n{system_instruction}\n\n"

        if recent_history:
            full_prompt += "Recent Conversation Context:\n"
            for turn in recent_history:
                speaker = config.USER_NAME if turn["role"] == "user" else config.ASSISTANT_NAME
                full_prompt += f"{speaker}: {turn['message']}\n"
            full_prompt += "\n"

        if web_search_context:
            full_prompt += f"Live Real-Time Web Intelligence:\n{web_search_context}\n"

        if context:
            full_prompt += f"Live Real-Time Data (Calendar / Emails / Tasks):\n{context}\n\n"

        full_prompt += f"Current Input ({config.USER_NAME}): {prompt}\n{config.ASSISTANT_NAME}:"

        max_tokens = 250 if channel == "voice" else 3500
        temperature = 0.4 if channel == "voice" else 0.5
        payload = {
            "contents": [
                {
                    "parts": [{"text": full_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
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

        # Common sense voice post-formatting
        if channel == "voice" and reply_text:
            reply_text = re.sub(r'\*{1,4}', '', reply_text)
            reply_text = re.sub(r'#{1,6}\s*', '', reply_text)
            reply_text = re.sub(r'^[•\-\*]\s*', '', reply_text, flags=re.MULTILINE)
            reply_text = reply_text.strip()

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

        # Meeting alert window change
        alert_match = re.search(r'(?:alert|warn|meeting notice)\s+(?:me\s+)?(\d{1,3})\s*(?:minutes?|mins?)', lower)
        if alert_match:
            mins = alert_match.group(1)
            self.memory.set_setting("meeting_alert_minutes", mins, "Advance meeting warning window")

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
            "i am in", "i live in", "my work", "don't call me", "i like ", "never ",
            "remember this preference", "note that i"
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
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={self.api_key}"
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
                with urllib.request.urlopen(req, timeout=12) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    candidates = result.get("candidates", [])
                    if candidates:
                        return candidates[0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                print(f"[-] Transcribe attempt with {model} failed: {e}")
                continue

        return ""

    def analyze_image(self, image_bytes: bytes, prompt: str, mime_type: str = "image/jpeg") -> str:
        """Analyzes an image using Gemini Multimodal Vision with Jarvis system personality."""
        system_inst = self._build_system_instruction()
        return self.vision.analyze_image(image_bytes, prompt, system_instruction=system_inst, mime_type=mime_type)
