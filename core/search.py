import config
import urllib.request
import urllib.parse
import re
import html
import logging
from typing import List, Dict, Any

logger = logging.getLogger("JarvisSearch")

class WebSearchEngine:
    """
    Lightweight, high-resilience web search engine.
    Extracts real-time live data (gold/silver prices, weather, news, sports scores,
    and factual market information) without requiring paid API subscriptions.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

    def search_ddg_html(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Scrapes primary DuckDuckGo HTML results."""
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=9) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', content, re.DOTALL)
                titles = re.findall(r'<h2 class="result__title">.*?<a[^>]*>(.*?)</a>', content, re.DOTALL)

                results = []
                for i in range(min(len(snippets), max_results)):
                    clean_title = html.unescape(re.sub(r'<[^>]+>', '', titles[i])).strip() if i < len(titles) else "Result"
                    clean_snip = html.unescape(re.sub(r'<[^>]+>', '', snippets[i])).strip()
                    if clean_snip:
                        results.append({"title": clean_title, "snippet": clean_snip})
                return results
        except Exception as e:
            logger.debug(f"DDG HTML search failed ({e})")
            return []

    def search_ddg_lite(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Scrapes DuckDuckGo Lite as an ultra-fast fallback."""
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        headers = {**self.headers, "Content-Type": "application/x-www-form-urlencoded"}
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
                    if clean_snip:
                        results.append({"title": clean_title, "snippet": clean_snip})
                return results
        except Exception as e:
            logger.debug(f"DDG Lite search failed ({e})")
            return []

    def search_web(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Executes search with dual-engine failover."""
        results = self.search_ddg_html(query, max_results)
        if not results:
            results = self.search_ddg_lite(query, max_results)
        return results

    def should_search_web(self, query: str) -> bool:
        """Determines if the user's prompt requires real-time live web data."""
        lower = query.lower()

        # Direct search signals
        if any(lower.startswith(prefix) for prefix in ["search ", "google ", "look up ", "browse ", "find online "]):
            return True

        # Real-time topics
        live_keywords = [
            "gold", "silver", "rate", "price", "stock", "sensex", "nifty", "shares",
            "weather", "temperature", "forecast", "rain", "aqi", "air quality",
            "petrol", "diesel", "fuel", "cng",
            "news", "headline", "breaking", "latest update", "current affairs",
            "cricket", "match", "score", "ipl", "fifa", "who won", "standings",
            "flight status", "train status", "currency rate", "exchange rate",
            "today", "current", "now", "live", "at present"
        ]

        # Ignore internal assistant commands
        internal_signals = ["email", "calendar", "schedule", "my agenda", "remind me", "voice model", "briefing", "my task", "note "]
        if any(signal in lower for signal in internal_signals) and not any(kw in lower for kw in ["gold", "weather", "petrol", "stock", "news"]):
            return False

        return any(kw in lower for kw in live_keywords)

    def build_search_query(self, user_query: str, location_dict: Dict[str, str]) -> str:
        """
        Enhances the user query with location details (City, State, Country)
        if the query is geographically sensitive and lacks an explicit location.
        """
        clean_q = re.sub(r'^(?:jarvis|service|assistant|please|can you|could you|tell me|what is|how much is)\s+', '', user_query, flags=re.IGNORECASE).strip()
        lower = clean_q.lower()
        city = location_dict.get("city", "Delhi")
        country = location_dict.get("country", "India")

        # Commodity / Gold price enhancement
        if "gold" in lower or "silver" in lower:
            if not any(c.lower() in lower for c in [city.lower(), "delhi", "mumbai", "kolkata", "chennai", "bangalore"]):
                return f"today 24k 22k gold rate in {city} {country} per gram inr"
            else:
                return f"{clean_q} 24k 22k per gram inr today"

        # Weather enhancement
        if any(w in lower for w in ["weather", "temperature", "forecast", "aqi"]):
            if not any(c.lower() in lower for c in [city.lower(), "delhi", "mumbai", "kolkata", "chennai", "bhubaneswar"]):
                return f"weather forecast today {city} {country}"

        # Fuel price enhancement
        if any(f in lower for f in ["petrol", "diesel", "fuel", "cng"]):
            if not any(c.lower() in lower for c in [city.lower(), "delhi", "mumbai"]):
                return f"petrol diesel price today {city} {country} inr per litre"

        return clean_q

    def format_search_results(self, results: List[Dict[str, str]]) -> str:
        """Formats structured search snippets for Gemini prompt injection."""
        if not results:
            return "No recent web search results found."
        lines = []
        for idx, res in enumerate(results, 1):
            lines.append(f"[{idx}] {res['title']}\nSnippet: {res['snippet']}")
        return "\n\n".join(lines)
