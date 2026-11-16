# Jarvis Personal AI Assistant 🎙️

An autonomous, multi-modal personal assistant designed for mobile productivity via Telegram, powered by Google Gemini, neural voice synthesis, and direct Google Workspace integrations.

---

## 🌟 Key Features

- **🧠 Cognitive Brain (Google Gemini)**:
  - Multi-model failover support across responsive Gemini Flash tiers.
  - Strict safety protocols: Read-only defaults, zero deletions, and two-phase confirmation for critical actions.
  - Windows IPv4 DNS optimization to eliminate socket timeouts.

- **🎙️ Voice & Conversational Intelligence**:
  - **Hands-Free Desktop Wake-Word ("Jarvis")**: Call *"Jarvis"* or *"Hey Jarvis"* out loud at your desk. It detects your voice using an offline ONNX wake-word engine, plays an activation chime, records your query, and speaks back through your laptop speakers!
  - **Voice Notes in Telegram**: Speak directly to Jarvis via Telegram voice messages. Jarvis transcribes using Gemini's native audio model and replies with a spoken voice note.
  - **Neural Text-to-Speech (Edge-TTS)**: Lifelike neural voice synthesis with multiple selectable voices (Prabhat Indian 🇮🇳, Brian Global 🌐, Neerja Female 🇮🇳, Christopher US 🇺🇸, Ryan British 🇬🇧).
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

- **💻 Laptop OS & System Commander (Win32 Native)**:
  - **Hardware Telemetry**: Voice and text queries for battery percentage, charging status, RAM usage, CPU load, and disk storage.
  - **Native Audio & Screen Controls**: Hands-free master volume adjustment (`"Jarvis, volume 40%"`), mute/unmute, and display brightness dimming.
  - **Application & Website Launcher**: Launch local apps (`"Jarvis, open VS Code"`, `"Jarvis, open Spotify"`) and websites (`"Jarvis, open YouTube"`).
  - **Workstation Security**: Instant security lock (`"Jarvis, lock the laptop"` or remote Telegram `/lock`) and sleep mode.
  - **Clipboard Intelligence**: Read, explain, or summarize whatever is copied on your Windows clipboard (`"Jarvis, explain what is on my clipboard"`).

- **👁️ Visual Perception & Multimodal Intelligence**:
  - **Desktop Screen Awareness**: Instant screenshot capture and analysis with Gemini Vision (`"Jarvis, explain what is on my screen"` or `/screen`). Reviews code, debugs terminal errors, and summarizes web pages.
  - **Webcam Sight**: Live camera frame capture (`"Jarvis, what am I holding?"` or `/webcam`). Recognizes objects, physical documents, books, and surroundings.
  - **Photo Message Inspector**: Send any photo on Telegram with an optional question to receive an executive visual breakdown and voice note.

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

You have multiple convenient launch modes:

* **Unified Dual Mode (Desktop Wake-Word + Telegram Bot)**:
  ```bash
  python main.py
  ```
  *(or `python main.py --all`)*

* **Hands-Free Desktop Voice Only** (Speak *"Jarvis"* at your laptop without Telegram):
  ```bash
  python main.py --voice
  ```

* **Telegram Companion Bot Only**:
  ```bash
  python main.py --telegram
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
| `/system` | Live workstation telemetry (battery %, RAM, CPU, storage, volume) |
| `/lock` | Remotely lock Windows workstation immediately from your phone |
| `/volume <0-100>` | Inspect or adjust laptop master audio volume |
| `/mute` / `/unmute` | Silence or restore laptop speakers |
| `/open <app or url>` | Launch apps (VS Code, Chrome, Spotify) or websites on laptop |
| `/clipboard` | Inspect text currently copied to your Windows clipboard |
| `/screen [query]` | Capture live desktop screenshot with Gemini multimodal visual analysis |
| `/webcam [query]` | Capture live webcam photo with object, document, or room description |
| `/status` | Diagnostic health check of all assistant subsystems |

---

## 📂 Project Architecture

```
Jarvis/
├── main.py                     # Unified CLI launcher & diagnostics runner
├── config.py                   # Environment config & IPv4 DNS optimization
├── jarvis_memory.db            # SQLite persistent memory (tasks & notes)
├── ROADMAP.md                  # Comprehensive phased evolution roadmap
├── core/
│   ├── brain.py                # Gemini API client with audio transcription & failover
│   ├── system_commander.py     # Win32 native laptop OS controller (audio, telemetry, apps)
│   ├── vision.py               # Multimodal screen grabber, webcam vision & image reasoning
│   ├── memory.py               # SQLite storage manager for tasks & notes
│   ├── location.py             # Dynamic GPS & regional calibration engine
│   ├── search.py               # Real-time web intelligence extractor
│   └── scheduler.py            # Autonomous background scheduler & guardians
├── integrations/
│   ├── google_services.py      # Google Calendar & Gmail HTTP client with auto-refresh
│   └── telegram_bot.py         # Telegram companion bot with voice & text handlers
├── voice/
│   ├── listener.py             # Hands-free local ONNX wake-word voice assistant
│   ├── chimes.py               # Synthesized audio feedback chimes
│   ├── ui_notify.py            # Native Windows desktop toast notifications
│   └── tts.py                  # Edge-TTS neural speech synthesis engine
└── temp_audio/                 # Generated voice responses cache
```
