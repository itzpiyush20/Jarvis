import sys
import os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from google_auth_oauthlib.flow import InstalledAppFlow

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

auth_code = None

class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <html>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #2e7d32;">Authentication Successful!</h1>
                <p>Google Calendar and Gmail are now connected to Jarvis.</p>
                <p>You may close this tab and return to your chat.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication failed. No code received.</h1>")

    def log_message(self, format, *args):
        pass  # Quiet logs

def main():
    global auth_code
    cred_file = PROJECT_ROOT / "credentials.json"
    token_file = PROJECT_ROOT / "token.json"

    if not cred_file.exists():
        print(f"[-] ERROR: {cred_file} not found.")
        return

    # Allow insecure localhost transport for OAuth 2.0
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
    flow.redirect_uri = "http://localhost:8080/"
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")

    with open(PROJECT_ROOT / "auth_url.txt", "w", encoding="utf-8") as f:
        f.write(auth_url)

    print("\n" + "=" * 60)
    print("PLEASE OPEN THIS URL IN YOUR BROWSER:")
    print(auth_url)
    print("=" * 60 + "\n")

    server = HTTPServer(("localhost", 8080), OAuthHandler)
    print("[*] Waiting for authorization on http://localhost:8080/ ...")
    while not auth_code:
        server.handle_request()

    print("[*] Exchanging authorization code for access tokens...")
    flow.fetch_token(code=auth_code)
    creds = flow.credentials

    with open(token_file, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print("\n" + "=" * 60)
    print("[+] SUCCESS! token.json has been created and saved!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
