import config
import json
import logging
import urllib.request
import urllib.parse
import re
from typing import Dict, Optional
from core.memory import MemoryManager

logger = logging.getLogger("JarvisLocation")

class LocationManager:
    """
    Manages user location, geocoding, and reverse geocoding.
    Provides local regional context (city, state, country) for all queries
    such as weather, gold prices, local market trends, and events.
    """

    def __init__(self, memory: Optional[MemoryManager] = None):
        self.memory = memory or MemoryManager()

    def get_user_location(self) -> Dict[str, str]:
        """
        Retrieves the user's current location from persistent settings,
        falling back to default Indian national context if not set.
        """
        city = self.memory.get_setting("user_city", "New Delhi")
        state = self.memory.get_setting("user_state", "Delhi")
        country = self.memory.get_setting("user_country", "India")

        display = f"{city}, {state}, {country}".replace(", ,", ",").strip(", ")
        return {
            "city": city,
            "state": state,
            "country": country,
            "display": display
        }

    def update_from_coordinates(self, lat: float, lon: float) -> Dict[str, str]:
        """
        Reverse-geocodes latitude and longitude from Telegram location pin
        using OpenStreetMap Nominatim.
        """
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        headers = {"User-Agent": "JarvisAssistant/2.0 (itzpiyush20)"}

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                addr = data.get("address", {})
                city = addr.get("city") or addr.get("town") or addr.get("suburb") or addr.get("state_district") or "Local Area"
                state = addr.get("state", "")
                country = addr.get("country", "India")

                # Store in persistent settings
                self.memory.set_setting("user_city", city, "User confirmed city")
                self.memory.set_setting("user_state", state, "User confirmed state")
                self.memory.set_setting("user_country", country, "User confirmed country")
                self.memory.set_setting("user_latitude", str(lat), "User GPS latitude")
                self.memory.set_setting("user_longitude", str(lon), "User GPS longitude")

                display = f"{city}, {state}, {country}".replace(", ,", ",").strip(", ")
                self.memory.add_learning(f"User primary location updated to {display}.", category="context")

                return {
                    "city": city,
                    "state": state,
                    "country": country,
                    "display": display
                }
        except Exception as e:
            logger.error(f"[-] Reverse geocoding failed: {e}")
            return self.get_user_location()

    def set_manual_location(self, location_text: str) -> Dict[str, str]:
        """
        Allows setting location via text (e.g. 'Bhubaneswar', 'Mumbai', 'New Delhi').
        Uses Nominatim Search to resolve exact city, state, and country.
        """
        clean_query = location_text.strip().title()
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(clean_query)}&format=json&limit=1"
        headers = {"User-Agent": "JarvisAssistant/2.0 (itzpiyush20)"}

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data:
                    display_name = data[0].get("display_name", "")
                    parts = [p.strip() for p in display_name.split(",")]
                    city = clean_query
                    state = ""
                    country = "India"
                    if len(parts) >= 2:
                        city = parts[0]
                        country = parts[-1]
                        state = parts[-3] if len(parts) >= 3 else parts[-2]

                    self.memory.set_setting("user_city", city, "Manual user city")
                    self.memory.set_setting("user_state", state, "Manual user state")
                    self.memory.set_setting("user_country", country, "Manual user country")

                    disp = f"{city}, {state}, {country}".replace(", ,", ",").strip(", ")
                    self.memory.add_learning(f"User location updated to {disp}.", category="context")
                    return {"city": city, "state": state, "country": country, "display": disp}
        except Exception as e:
            logger.warning(f"Nominatim search failed for '{location_text}': {e}")

        # Direct fallback save
        self.memory.set_setting("user_city", clean_query, "Manual user city")
        self.memory.add_learning(f"User location set to {clean_query}.", category="context")
        return {"city": clean_query, "state": "", "country": "India", "display": f"{clean_query}, India"}

    def detect_and_handle_location_change(self, text: str) -> Optional[Dict[str, str]]:
        """Detects if user is updating their location via conversational text."""
        lower = text.lower()
        patterns = [
            r'(?:i am in|i am at|i live in|my city is|my location is|set my location to|update location to|moved to)\s+([a-zA-Z\s,]+)',
            r'(?:currently in|staying in)\s+([a-zA-Z\s,]+)'
        ]
        for pat in patterns:
            match = re.search(pat, lower)
            if match:
                loc_cand = match.group(1).strip()
                # Exclude false positives
                if loc_cand and len(loc_cand) < 40 and not any(w in loc_cand for w in ["hurry", "meeting", "call", "trouble", "touch"]):
                    return self.set_manual_location(loc_cand)
        return None
