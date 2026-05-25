import httpx, logging, config, trafilatura, re
from retry import retry_async

logger = logging.getLogger(__name__)

def _clean_tavily_content(text: str) -> str:
    if not text: return ""
    clean = trafilatura.extract(text, include_comments=False, include_tables=False, fallback_to_scraper=False)
    if clean: return ' '.join(clean.split()).strip()
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[*_#~`>]', '', text)
    return ' '.join(text.split()).strip()

@retry_async()
async def fetch_tavily(query: str, time_range: str = "") -> str:
    if not config.TAVILY_API_KEY: return ""
    payload = {"query": query, "include_answer": False, "search_depth": "basic", "max_results": config.MAX_SEARCH_RESULTS, "include_raw_content": True, "exclude_domains": ["youtube.com"], "api_key": config.TAVILY_API_KEY}
    if time_range in ("day", "week", "month", "year"): payload["time_range"] = time_range
    async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
        r = await client.post("https://api.tavily.com/search", json=payload)
        if r.status_code != 200: return ""
        parts = []
        for res in r.json().get("results", [])[:config.MAX_SEARCH_RESULTS]:
            raw = res.get("raw_content") or res.get("content") or ""
            if not raw: continue
            clean = _clean_tavily_content(raw)
            if len(clean) < 50: continue
            parts.append(f"🔹 {res.get('title', '')}: {clean[:config.MAX_LINK_CONTENT_SIZE]}")
        return "\n".join(parts) if parts else ""
