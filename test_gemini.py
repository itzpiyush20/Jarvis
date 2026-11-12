"""
Jarvis API Key Verification Script
Tests your Gemini API key directly using the JarvisBrain engine.
"""
from core.brain import JarvisBrain

def main():
    print("[*] Initializing Jarvis Brain with your API key...")
    brain = JarvisBrain()
    print("[*] Sending test prompt to Jarvis...")
    reply = brain.ask("Jarvis, report status and confirm you are ready.")
    print("\n" + "=" * 55)
    print("[+] RESPONSE FROM JARVIS:")
    print(f"    {reply}")
    print("=" * 55 + "\n")

if __name__ == "__main__":
    main()
