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
    """Fast, direct HTTP integration for Google Calendar and Gmail with auto-refresh."""

    def __init__(self):
        self._token_data = {}
        self.load_token()

    def is_configured(self) -> bool:
        return TOKEN_FILE.exists() or bool(os.getenv("GOOGLE_TOKEN_JSON"))

    def load_token(self):
        token_env = os.getenv("GOOGLE_TOKEN_JSON")
        if token_env and not TOKEN_FILE.exists():
            try:
                self._token_data = json.loads(token_env)
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._token_data, f, indent=2)
                return
            except Exception as e:
                print(f"[-] Error parsing GOOGLE_TOKEN_JSON env var: {e}")

        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                    self._token_data = json.load(f)
            except Exception as e:
                print(f"[-] Error loading token.json: {e}")

    def is_token_expired(self) -> bool:
        """Checks if the access token has expired or will expire within 60 seconds."""
        expiry = self._token_data.get("expiry")
        if not expiry:
            return False
        try:
            exp_clean = expiry.replace("Z", "+00:00")
            exp_dt = datetime.datetime.fromisoformat(exp_clean)
            return datetime.datetime.now(datetime.timezone.utc) >= (exp_dt - datetime.timedelta(seconds=60))
        except Exception:
            return False

    def refresh_token(self) -> bool:
        """Refreshes the OAuth access token using the stored refresh_token."""
        refresh_token = self._token_data.get("refresh_token")
        client_id = self._token_data.get("client_id")
        client_secret = self._token_data.get("client_secret")
        token_uri = self._token_data.get("token_uri", "https://oauth2.googleapis.com/token")

        if not (refresh_token and client_id and client_secret):
            return False

        payload = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }).encode("utf-8")

        req = urllib.request.Request(
            token_uri,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                new_token = data.get("access_token")
                if new_token:
                    self._token_data["token"] = new_token
                    if "expires_in" in data:
                        new_expiry = (
                            datetime.datetime.now(datetime.timezone.utc) +
                            datetime.timedelta(seconds=data["expires_in"])
                        ).isoformat()
                        self._token_data["expiry"] = new_expiry
                    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                        json.dump(self._token_data, f, indent=2)
                    return True
        except Exception as e:
            print(f"[-] Failed to refresh Google OAuth token: {e}")
        return False

    def get_token(self) -> Optional[str]:
        if not self._token_data:
            self.load_token()
        if self.is_token_expired():
            self.refresh_token()
        return self._token_data.get("token")

    def _get(self, url: str, retry_on_401: bool = True) -> Optional[Dict[str, Any]]:
        token = self.get_token()
        if not token:
            return None
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry_on_401:
                if self.refresh_token():
                    return self._get(url, retry_on_401=False)
            print(f"[-] Google GET HTTP {e.code} ({url[:60]}...): {e.reason}")
            return None
        except Exception as e:
            print(f"[-] Google GET error ({url[:60]}...): {e}")
            return None

    def _post(self, url: str, payload: Dict[str, Any], retry_on_401: bool = True) -> Optional[Dict[str, Any]]:
        token = self.get_token()
        if not token:
            return None
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry_on_401:
                if self.refresh_token():
                    return self._post(url, payload, retry_on_401=False)
            print(f"[-] Google POST HTTP {e.code}: {e.reason}")
            return None
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
            end = item.get("end", {}).get("dateTime", item.get("end", {}).get("date"))
            events.append({
                "id": item.get("id", ""),
                "summary": item.get("summary", "(Untitled Event)"),
                "start": start,
                "end": end,
                "description": item.get("description", ""),
                "location": item.get("location", ""),
                "link": item.get("htmlLink", "")
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

    def create_event(
        self,
        summary: str,
        start_time_iso: str,
        end_time_iso: str,
        description: str = "",
        location: str = ""
    ) -> Optional[Dict[str, Any]]:
        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        payload = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time_iso},
            "end": {"dateTime": end_time_iso}
        }
        return self._post(url, payload)

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
                "id": msg["id"],
                "from": sender,
                "subject": subject,
                "snippet": detail.get("snippet", "")[:120]
            })
        return email_list

    def check_urgent_emails(self, max_results: int = 10, keywords: Optional[List[str]] = None) -> List[Dict[str, str]]:
        """Scans unread emails for urgent keywords."""
        if keywords is None:
            keywords = ["urgent", "important", "action required", "immediate", "alert", "critical", "asap", "emergency"]
        unreads = self.get_unread_emails(max_results=max_results)
        urgent = []
        for em in unreads:
            text = f"{em.get('subject', '')} {em.get('snippet', '')}".lower()
            if any(k in text for k in keywords):
                urgent.append(em)
        return urgent

if __name__ == "__main__":
    gs = GoogleServices()
    print("Testing agenda:", gs.format_daily_agenda())
    emails = gs.get_unread_emails(max_results=2)
    print(f"Testing emails ({len(emails)}):", emails)
    urgent = gs.check_urgent_emails()
    print(f"Testing urgent emails ({len(urgent)}):", urgent)
