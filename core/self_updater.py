import os
import json
import base64
import urllib.request
import urllib.error
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("JarvisSelfUpdater")

REPO_OWNER = "itzpiyush20"
REPO_NAME = "Jarvis"

class JarvisSelfUpdater:
    """
    Enables Jarvis to autonomously read, modify, and push updates
    to his own GitHub repository, triggering automated cloud redeployment.
    """

    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.github_token)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Jarvis-Autonomous-Self-Updater"
        }

    def get_file_content(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw content and SHA of a file from the GitHub repository."""
        if not self.is_configured():
            return None
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{file_path}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = base64.b64decode(data.get("content", "")).decode("utf-8")
                return {
                    "sha": data.get("sha"),
                    "content": content
                }
        except Exception as e:
            logger.error(f"[-] Failed to fetch {file_path} from GitHub: {e}")
            return None

    def commit_file_update(self, file_path: str, new_content: str, commit_message: str) -> bool:
        """Commits and pushes an updated file directly to the GitHub repository."""
        if not self.is_configured():
            logger.warning("[-] Cannot commit update: GITHUB_TOKEN is not configured.")
            return False

        existing = self.get_file_content(file_path)
        sha = existing.get("sha") if existing else None

        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{file_path}"
        encoded_bytes = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")

        payload = {
            "message": commit_message,
            "content": encoded_bytes,
            "branch": "main"
        }
        if sha:
            payload["sha"] = sha

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **self._headers()},
            method="PUT"
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                logger.info(f"[+] Successfully committed {file_path} to GitHub: {commit_message}")
                return True
        except Exception as e:
            logger.error(f"[-] Failed to commit file update to GitHub: {e}")
            return False
