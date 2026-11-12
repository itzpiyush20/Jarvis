import datetime
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = PROJECT_ROOT / "token.json"

class GoogleServices:
    """Fast, direct HTTP integration for Google Calendar and Gmail."""

    def __init__(self):
        self._token_data = {}
        self.load_token()

    def is_configured(self) -> bool:
        return TOKEN_FILE.exists()

    def load_token(self):
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                    self._token_data = json.load(f)
            except Exception as e:
                print(f"[-] Error loading token.json: {e}")

    def get_token(self) -> Optional[str]:
        if not self._token_data:
            self.load_token()
        return self._token_data.get("token")

    def _get(self, url: str) -> Optional[Dict[str, Any]]:
        token = self.get_token()
        if not token:
            return None
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[-] Google GET error ({url[:60]}...): {e}")
            return None

    def _post(self, url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        token = self.get_token()
        if not token:
            return None
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[-] Google POST error: {e}")
            return None

    # ------------------ CALENDAR ------------------ #

    def get_upcoming_events(self, max_results: int = 5) -> List[Dict[str, Any]]:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        encoded_now = urllib.parse.quote(now)
        url = (
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events?"
            f"timeMin={encoded_now}&maxResults={max_results}&singleEvents=true&orderBy=startTime"
        )
        data = self._get(url)
        if not data:
            return []
        events = []
        for item in data.get("items", []):
            start = item.get("start", {}).get("dateTime", item.get("start", {}).get("date"))
            events.append({
                "summary": item.get("summary", "(Untitled Event)"),
                "start": start
            })
        return events

    def format_daily_agenda(self) -> str:
        events = self.get_upcoming_events(max_results=5)
        if not events:
            return "You have no upcoming events scheduled on your calendar, Sir."
        lines = ["Here is your upcoming schedule, Sir:"]
        for ev in events:
            lines.append(f"• {ev['summary']} (at {ev['start']})")
        return "\n".join(lines)

    # ------------------ GMAIL ------------------ #

    def get_unread_emails(self, max_results: int = 5) -> List[Dict[str, str]]:
        query = urllib.parse.quote("is:unread label:INBOX")
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={max_results}&q={query}"
        data = self._get(url)
        if not data:
            return []
        email_list = []
        for msg in data.get("messages", []):
            msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}?format=metadata"
            detail = self._get(msg_url)
            if not detail:
                continue
            headers = detail.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(No Subject)")
            sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown")
            email_list.append({
                "from": sender,
                "subject": subject,
                "snippet": detail.get("snippet", "")[:120]
            })
        return email_list

if __name__ == "__main__":
    gs = GoogleServices()
    print("Testing agenda:", gs.format_daily_agenda())
    emails = gs.get_unread_emails(max_results=2)
    print(f"Testing emails ({len(emails)}):", emails)
