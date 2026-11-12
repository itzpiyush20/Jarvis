import datetime
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"

class GoogleServices:
    """Manages integration with Google Calendar and Gmail via OAuth 2.0."""

    def __init__(self):
        self.creds: Optional[Credentials] = None
        self._calendar_service = None
        self._gmail_service = None
        self.authenticate()

    def is_configured(self) -> bool:
        """Returns True if credentials.json or token.json exists."""
        return TOKEN_FILE.exists() or CREDENTIALS_FILE.exists()

    def authenticate(self):
        """Loads cached token or initiates desktop browser authorization."""
        if TOKEN_FILE.exists():
            self.creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                        f.write(self.creds.to_json())
                except Exception as e:
                    print(f"[-] Token refresh failed: {e}")
                    self.creds = None

            if not self.creds and CREDENTIALS_FILE.exists():
                print("[*] Launching browser to authorize Google Workspace (Calendar & Gmail)...")
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
                self.creds = flow.run_local_server(port=0)
                with open(TOKEN_FILE, "w", encoding="utf-8") as token:
                    token.write(self.creds.to_json())
                print("[+] Successfully authorized and saved token.json!")

        if self.creds and self.creds.valid:
            self._calendar_service = build("calendar", "v3", credentials=self.creds)
            self._gmail_service = build("gmail", "v1", credentials=self.creds)

    # ------------------ GOOGLE CALENDAR ------------------ #

    def get_upcoming_events(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """Fetches upcoming calendar events starting from now."""
        if not self._calendar_service:
            return []

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        events_result = (
            self._calendar_service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        formatted = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            formatted.append({
                "id": event.get("id"),
                "summary": event.get("summary", "(No Title)"),
                "start": start,
                "location": event.get("location", ""),
                "description": event.get("description", ""),
            })
        return formatted

    def create_event(
        self,
        summary: str,
        start_time_iso: str,
        end_time_iso: str,
        description: str = "",
        location: str = ""
    ) -> Dict[str, Any]:
        """Creates a new calendar event."""
        if not self._calendar_service:
            raise RuntimeError("Google Calendar service not authenticated.")

        event_body = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": {"dateTime": start_time_iso, "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_time_iso, "timeZone": "Asia/Kolkata"},
        }
        return self._calendar_service.events().insert(calendarId="primary", body=event_body).execute()

    def format_daily_agenda(self) -> str:
        """Formats upcoming events into a human/speech-friendly summary."""
        events = self.get_upcoming_events(max_results=5)
        if not events:
            return "You have no upcoming events on your calendar, Sir. Your schedule is clear."

        lines = ["Here is your upcoming schedule:"]
        for ev in events:
            time_str = ev["start"]
            lines.append(f"• {ev['summary']} at {time_str}")
        return "\n".join(lines)

    # ------------------ GMAIL ------------------ #

    def get_unread_emails(self, max_results: int = 5) -> List[Dict[str, str]]:
        """Fetches unread emails from the inbox."""
        if not self._gmail_service:
            return []

        results = (
            self._gmail_service.users()
            .messages()
            .list(userId="me", q="is:unread label:INBOX", maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])
        email_list = []

        for msg in messages:
            msg_data = (
                self._gmail_service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="metadata")
                .execute()
            )
            headers = msg_data.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
            sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown")
            snippet = msg_data.get("snippet", "")

            email_list.append({
                "id": msg["id"],
                "from": sender,
                "subject": subject,
                "snippet": snippet,
            })
        return email_list

    def check_urgent_emails(self) -> List[Dict[str, str]]:
        """Scans unread emails for urgent keywords."""
        keywords = ["urgent", "important", "action required", "immediate", "alert", "critical"]
        unreads = self.get_unread_emails(max_results=10)
        urgent = []
        for email in unreads:
            text_to_check = (email["subject"] + " " + email["snippet"]).lower()
            if any(k in text_to_check for k in keywords):
                urgent.append(email)
        return urgent

if __name__ == "__main__":
    gs = GoogleServices()
    if not gs.is_configured():
        print("[!] Google Workspace is not configured yet.")
        print("    Please place your 'credentials.json' (Desktop App Client ID) in the Jarvis root folder.")
    else:
        print("[+] Testing Google Services connection...")
        agenda = gs.format_daily_agenda()
        print(f"[+] Agenda: {agenda}")
