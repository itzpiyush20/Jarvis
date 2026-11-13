# Jarvis Personal AI Assistant 🎙️

An autonomous, multi-modal personal assistant designed for mobile productivity via Telegram, powered by Google Gemini, neural voice synthesis, and direct Google Workspace integrations.

---

## 🌟 Key Features

- **🧠 Cognitive Brain (Google Gemini)**:
  - Multi-model failover support across responsive Gemini Flash tiers.
  - Strict safety protocols: Read-only defaults, zero deletions, and two-phase confirmation for critical actions.
  - Windows IPv4 DNS optimization to eliminate socket timeouts.

- **🎙️ Voice & Conversational Intelligence**:
  - **Voice Notes in Telegram**: Speak directly to Jarvis via Telegram voice messages. Jarvis transcribes using Gemini's native audio model and replies with a spoken voice note.
  - **Neural Text-to-Speech (Edge-TTS)**: British neural voice (`en-GB-RyanNeural`) synthesizing lifelike spoken responses.
  - `/voice <query>`: Request spoken audio responses on demand.

- **📅 Google Workspace Integrations**:
  - **Google Calendar**: Retrieve upcoming meetings, daily agenda formatting, and proactive meeting alerts.
  - **Gmail**: Unread message scanning, urgent email triage, and sender/subject alerts.
  - **Auto-Refreshing OAuth**: Seamless background token refresh without requiring browser re-authorization.

- **⏰ Autonomous Background Scheduler**:
  - **Morning Briefing**: Automated daily briefing delivered at 8:00 AM containing schedule, inbox highlights, and urgent tasks.
  - **Meeting Guardian**: Scans for upcoming meetings and proactively alerts 10–15 minutes before start.
  - **Urgent Email Monitor**: Periodically scans inbox for high-priority/urgent emails and alerts immediately.
  - **On-Demand Briefings**: Use `/briefing` at any time for an instant audio and text report.

- **💾 Persistent SQLite Memory**:
  - Long-term note taking and task management with urgency and due-date tracking.

---

## 🚀 Quickstart

### 1. Requirements & Setup
Ensure dependencies are installed:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Copy `.env.example` to `.env` and provide your keys:
```env
GEMINI_API_KEY=your_gemini_api_key
TELEGRAM_BOT_TOKEN=your_botfather_token
TELEGRAM_USER_ID=your_telegram_numeric_id
ASSISTANT_NAME=Jarvis
USER_NAME=Sir
```

### 3. Google Workspace OAuth
Place your Google Cloud OAuth client credentials in `credentials.json` and authenticate once:
```bash
python auth_google.py
```
This generates `token.json`, which is automatically refreshed by Jarvis going forward.

### 4. Run System Diagnostics
Verify that all subsystems are online and healthy:
```bash
python main.py --status
```

### 5. Launch Jarvis
Start the full Jarvis assistant service (Telegram bot + background scheduler):
```bash
python main.py
```

---

## 📱 Telegram Commands & Usage

| Command | Description |
| :--- | :--- |
| **Send Voice Note** 🎙️ | Speak to Jarvis naturally; receives a transcribed answer + voice reply |
| `/start` | Connect with Jarvis and view available capabilities |
| `/briefing` | On-demand spoken audio & text daily briefing |
| `/agenda` | View your upcoming Google Calendar meetings |
| `/emails` | Review recent unread Gmail messages |
| `/alert <msg>` | Trigger an immediate high-priority audio alarm |
| `/tasks` | View pending tasks and urgent to-dos |
| `/note <text>` | Save a note into long-term SQLite memory |
| `/voice <query>` | Ask Jarvis any question and get a spoken voice response |
| `/status` | Diagnostic health check of all assistant subsystems |

---

## 📂 Project Architecture

```
Jarvis/
├── main.py                     # Unified CLI launcher & diagnostics runner
├── config.py                   # Environment config & IPv4 DNS optimization
├── jarvis_memory.db            # SQLite persistent memory (tasks & notes)
├── core/
│   ├── brain.py                # Gemini API client with audio transcription & failover
│   ├── memory.py               # SQLite storage manager for tasks & notes
│   └── scheduler.py            # Autonomous background scheduler & guardians
├── integrations/
│   ├── google_services.py      # Google Calendar & Gmail HTTP client with auto-refresh
│   └── telegram_bot.py         # Telegram companion bot with voice & text handlers
├── voice/
│   └── tts.py                  # Edge-TTS neural speech synthesis engine
└── temp_audio/                 # Generated voice responses cache
```
