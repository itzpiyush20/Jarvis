import config
import urllib.request
import urllib.parse
import json
import xml.etree.ElementTree as ET
import re
import html
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("JarvisSearch")

class WebSearchEngine:
    """
    High-resilience, multi-engine real-time web intelligence for Jarvis.
    Combines:
    1. DuckDuckGo HTML & Lite (form-POST with bot-challenge bypass)
    2. Google News RSS for real-time news headlines & breaking developments
    3. wttr.in for real-time meteorological conditions and forecasts
    4. Wikipedia Open REST API for factual and encyclopedic inquiries
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def search_ddg_post(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Scrapes DuckDuckGo HTML using form POST to avoid GET-based bot challenges."""
        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        headers = {
            **self.headers,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://html.duckduckgo.com/"
        }
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=9) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', content, re.DOTALL)
                titles = re.findall(r'<h2 class="result__title">.*?<a[^>]*>(.*?)</a>', content, re.DOTALL)

                results = []
                for i in range(min(len(snippets), max_results)):
                    clean_title = html.unescape(re.sub(r'<[^>]+>', '', titles[i])).strip() if i < len(titles) else "Result"
                    clean_snip = html.unescape(re.sub(r'<[^>]+>', '', snippets[i])).strip()
                    if clean_snip and "bots use duckduckgo" not in clean_snip.lower():
                        results.append({"title": clean_title, "snippet": clean_snip, "source": "DuckDuckGo"})
                return results
        except Exception as e:
            logger.debug(f"DDG POST search error: {e}")
            return []

    def search_ddg_lite(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """DuckDuckGo Lite fallback via POST."""
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        headers = {
            **self.headers,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://lite.duckduckgo.com/"
        }
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=9) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                snippets = re.findall(r'<td class="result-snippet">\s*(.*?)\s*</td>', content, re.DOTALL)
                titles = re.findall(r'<a class="result-link"[^>]*>(.*?)</a>', content, re.DOTALL)

                results = []
                for i in range(min(len(snippets), max_results)):
                    clean_title = html.unescape(re.sub(r'<[^>]+>', '', titles[i])).strip() if i < len(titles) else "Result"
                    clean_snip = html.unescape(re.sub(r'<[^>]+>', '', snippets[i])).strip()
                    if clean_snip and "bots use duckduckgo" not in clean_snip.lower():
                        results.append({"title": clean_title, "snippet": clean_snip, "source": "DDG Lite"})
                return results
        except Exception as e:
            logger.debug(f"DDG Lite search error: {e}")
            return []

    def search_news(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Fetches real-time news headlines and timestamps from Google News RSS."""
        try:
            clean_q = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={clean_q}&hl=en-IN&gl=IN&ceid=IN:en"
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=7) as resp:
                root = ET.fromstring(resp.read().decode("utf-8", errors="ignore"))
                items = root.findall(".//item")
                results = []
                for item in items[:max_results]:
                    title_elem = item.find("title")
                    title = title_elem.text if title_elem is not None else "News Update"
                    date_elem = item.find("pubDate")
                    pub_date = date_elem.text if date_elem is not None else ""
                    desc_elem = item.find("description")
                    desc = html.unescape(re.sub(r'<[^>]+>', '', desc_elem.text)) if desc_elem is not None and desc_elem.text else title
                    results.append({
                        "title": f"News: {title}",
                        "snippet": f"{desc} (Published: {pub_date})",
                        "source": "Google News"
                    })
                return results
        except Exception as e:
            logger.debug(f"Google News RSS error: {e}")
            return []

    def search_weather(self, city: str) -> List[Dict[str, str]]:
        """Fetches live meteorological conditions and forecast from wttr.in."""
        try:
            clean_city = urllib.parse.quote(city)
            url = f"https://wttr.in/{clean_city}?format=j1"
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                curr = data["current_condition"][0]
                desc = curr["weatherDesc"][0]["value"]
                temp = curr["temp_C"]
                feels = curr["FeelsLikeC"]
                humidity = curr["humidity"]
                wind = curr["windspeedKmph"]
                uv = curr.get("uvIndex", "N/A")
                forecast = data.get("weather", [{}])[0]
                min_t = forecast.get("mintempC", "")
                max_t = forecast.get("maxtempC", "")
                snippet = (
                    f"Current condition in {city}: {desc}, Temperature: {temp}°C (Feels like {feels}°C), "
                    f"Humidity: {humidity}%, Wind: {wind} km/h, UV Index: {uv}. "
                    f"Today's forecast: Min {min_t}°C / Max {max_t}°C."
                )
                return [{"title": f"Live Weather in {city}", "snippet": snippet, "source": "Live Weather"}]
        except Exception as e:
            logger.debug(f"wttr.in weather error: {e}")
            return []

    def search_wikipedia(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
        """Queries Wikipedia official API for verified factual and biographical data."""
        try:
            clean_q = urllib.parse.quote(query)
            url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={clean_q}&format=json&utf8=1"
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                search_res = data.get("query", {}).get("search", [])
                results = []
                for item in search_res[:max_results]:
                    title = item.get("title", "")
                    raw_snippet = item.get("snippet", "")
                    clean_snip = html.unescape(re.sub(r'<[^>]+>', '', raw_snippet)).strip()
                    if clean_snip:
                        results.append({"title": f"Wikipedia: {title}", "snippet": clean_snip, "source": "Wikipedia"})
                return results
        except Exception as e:
            logger.debug(f"Wikipedia search error: {e}")
            return []

    def search_web(self, query: str, location_dict: Optional[Dict[str, str]] = None, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Executes an intelligent, multi-tier search with automatic domain routing
        and seamless fallback.
        """
        lower = query.lower()
        results: List[Dict[str, str]] = []

        # 1. Specialized live weather routing
        if any(w in lower for w in ["weather", "temperature", "forecast", "rain", "climate", "aqi", "air quality"]):
            city = location_dict.get("city", "Delhi") if location_dict else "Delhi"
            w_res = self.search_weather(city)
            if w_res:
                results.extend(w_res)

        # 2. Specialized live news routing
        if any(n in lower for n in ["news", "headline", "breaking", "update", "current affairs", "latest on"]):
            news_res = self.search_news(query, max_results=3)
            if news_res:
                results.extend(news_res)

        # 3. DuckDuckGo POST primary search
        ddg_res = self.search_ddg_post(query, max_results=max_results)
        if ddg_res:
            results.extend(ddg_res)
        else:
            # Fallback to DDG Lite
            lite_res = self.search_ddg_lite(query, max_results=max_results)
            if lite_res:
                results.extend(lite_res)

        # 4. Wikipedia factual fallback if results are sparse
        if len(results) < 2 and not any(k in lower for k in ["price", "rate", "weather", "score", "gold", "silver", "fuel"]):
            wiki_res = self.search_wikipedia(query, max_results=3)
            if wiki_res:
                results.extend(wiki_res)

        # Deduplicate results by title
        seen = set()
        deduped = []
        for r in results:
            key = r["title"].strip().lower()
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped[:max_results]

    def should_search_web(self, query: str) -> bool:
        """
        Determines whether the user's prompt seeks real-time, factual, or internet data.
        """
        lower = query.lower().strip()

        # Ignore purely internal assistant commands if no external topic is mentioned
        internal_signals = [
            "show my calendar", "my agenda", "check email", "unread email",
            "my tasks", "my notes", "switch voice", "voice model", "status report",
            "system diagnostic", "who are you", "who am i", "set reminder to"
        ]
        if any(lower.startswith(sig) for sig in internal_signals):
            return False

        # Direct explicit search signals
        if any(lower.startswith(prefix) for prefix in [
            "search", "google", "look up", "browse", "find online", "find out", "check online"
        ]):
            return True

        # Common question openers seeking factual or current details
        question_patterns = [
            r'^(?:what|who|where|when|why|how)\s+(?:is|are|was|were|did|do|does|much|many|about)\b',
            r'^(?:tell me about|details on|information about|give me details|can you find|check)\b',
            r'\b(?:what happened|latest news|release date|net worth|founder|ceo of)\b'
        ]
        if any(re.search(pat, lower) for pat in question_patterns):
            # Check if it's asking about something real rather than conversational small talk
            if not any(st in lower for st in ["how are you", "what is your name", "what can you do"]):
                return True

        # Real-time, financial, commodity, and current event keywords
        live_keywords = [
            "gold", "silver", "rate", "price", "stock", "sensex", "nifty", "shares",
            "weather", "temperature", "forecast", "rain", "aqi", "air quality",
            "petrol", "diesel", "fuel", "cng",
            "news", "headline", "breaking", "latest update", "current affairs",
            "cricket", "match", "score", "ipl", "fifa", "who won", "standings",
            "flight status", "train status", "currency rate", "exchange rate",
            "today", "current", "now", "live", "at present", "recent", "latest"
        ]
        return any(kw in lower for kw in live_keywords)

    def build_search_query(self, user_query: str, location_dict: Dict[str, str]) -> str:
        """
        Synthesizes a clean, high-precision search query from the user's prompt,
        incorporating location context only when regionally relevant and not already specified.
        """
        clean_q = re.sub(
            r'^(?:jarvis|service|assistant|please|can you|could you|tell me|what is|how much is|check)\s+',
            '',
            user_query,
            flags=re.IGNORECASE
        ).strip()
        clean_q = re.sub(r'[?!.,;]+$', '', clean_q).strip()

        lower = clean_q.lower()
        city = location_dict.get("city", "Delhi") if location_dict else "Delhi"
        country = location_dict.get("country", "India") if location_dict else "India"

        # Commodity / Gold price enhancement
        if "gold" in lower or "silver" in lower:
            metro_cities = ["delhi", "mumbai", "kolkata", "chennai", "bangalore", "bhubaneswar", "hyderabad", "pune", "ahmedabad"]
            has_city = any(c in lower for c in metro_cities) or (city.lower() in lower)
            if not has_city:
                return f"today 24k 22k gold rate in {city} inr per gram"
            else:
                return f"{clean_q} inr per gram today"

        # Weather enhancement
        if any(w in lower for w in ["weather", "temperature", "forecast", "aqi"]):
            if not (city.lower() in lower or any(c in lower for c in ["delhi", "mumbai", "bangalore", "kolkata"])):
                return f"weather forecast today {city}"

        # Fuel price enhancement
        if any(f in lower for f in ["petrol", "diesel", "fuel", "cng"]):
            if not (city.lower() in lower or any(c in lower for c in ["delhi", "mumbai"])):
                return f"petrol diesel price today {city} inr"

        return clean_q

    def format_search_results(self, results: List[Dict[str, str]]) -> str:
        """Formats structured search snippets for Gemini prompt injection."""
        if not results:
            return "No recent web search results found."
        lines = []
        for idx, res in enumerate(results, 1):
            source_tag = f"[{res.get('source', 'Web')}]"
            lines.append(f"{idx}. {source_tag} {res['title']}\n   Snippet: {res['snippet']}")
        return "\n\n".join(lines)
