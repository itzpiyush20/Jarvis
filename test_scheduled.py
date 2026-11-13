from core.brain import JarvisBrain
from integrations.google_services import GoogleServices

print("[*] Testing user prompt: 'Scheduled'...")
gs = GoogleServices()
agenda = gs.format_daily_agenda()
brain = JarvisBrain()
reply = brain.ask("Scheduled", context=agenda)
print("=" * 50)
print("REPLY:")
print(reply)
print("=" * 50)
