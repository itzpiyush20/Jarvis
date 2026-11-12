"""
Jarvis API Key Verification Script
Tests your Gemini API key directly against Google's endpoint.
No external dependencies required (uses standard library).
"""
import os
import json
import urllib.request
import urllib.error

def load_env_file(filepath=".env"):
    """Loads key-value pairs from .env without needing third-party libraries."""
    env_vars = {}
    if not os.path.exists(filepath):
        return env_vars
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars

def verify_gemini_key():
    env_vars = load_env_file()
    api_key = os.environ.get("GEMINI_API_KEY") or env_vars.get("GEMINI_API_KEY")

    if not api_key:
        print("[!] ERROR: GEMINI_API_KEY is not set.")
        print("    Please open your .env file in the Jarvis folder and paste your key:")
        print("    GEMINI_API_KEY=your_key_here\n")
        return False

    print(f"[*] Found API Key: ...{api_key[-4:] if len(api_key) > 4 else '****'}")
    print("[*] Connecting to Google Gemini API (gemini-1.5-flash)...")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Hello, respond with: 'Jarvis online and ready, sir!'"}
                ]
            }
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            candidate = result.get("candidates", [{}])[0]
            text = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
            print("\n" + "=" * 50)
            print("[+] SUCCESS! API Key is VALID and ACTIVE.")
            print(f"[+] Model Response: {text.strip()}")
            print("[+] You are connected to the Gemini Free Tier!")
            print("=" * 50 + "\n")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"\n[-] HTTP Error {e.code}: {e.reason}")
        print(f"[-] Details: {error_body}\n")
        return False
    except Exception as e:
        print(f"\n[-] Connection error: {e}\n")
        return False

if __name__ == "__main__":
    verify_gemini_key()
