import logging
import re
import config
import utils
import trafilatura
from retry import retry_async
from typing import List, Dict
import httpx
logger = logging.getLogger(__name__)

def _clean_tavily_content(text: str) -> str:
    if not text: return ""
    clean = trafilatura.extract(text, include_comments=False, include_tables=False, fallback_to_scraper=False)
    if clean:
        return ' '.join(clean.split()).strip()
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[*_#~`>]', '', text)
    return ' '.join(text.split()).strip()

@retry_async()
async def get_trending_topics_raw() -> List[Dict[str, any]]:
    async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
        r = await client.get("https://api.chainbase.com/tops/v1/tool/list-trending-topics", params={"language": "en"})
        if r.status_code != 200:
            logger.warning(f"[search] Chainbase trending failed: {r.status_code}")
            return []
        data = r.json()
        raw_items = data.get("items", [])
        filtered = [t for t in raw_items if utils.is_english(t.get("summary", ""))]
        trends = sorted(filtered, key=lambda x: x.get("current_rank", 999))[:10]
        return trends

@retry_async()
async def fetch_tavily(query: str, time_range: str = "") -> str:
    if not config.TAVILY_API_KEY: return ""
    payload = {
        "query": query,
        "include_answer": False,
        "search_depth": "basic",
        "max_results": config.MAX_SEARCH_RESULTS,
        "include_raw_content": True,
        "exclude_domains": ["youtube.com"],
        "api_key": config.TAVILY_API_KEY
    }
    if time_range in ("day", "week", "month", "year"):
        payload["time_range"] = time_range
    logger.info(f"[TAVILY REQUEST] query='{query}' | time_range='{time_range or 'none'}'")
    async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
        r = await client.post("https://api.tavily.com/search", json=payload)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            parts = []
            for res in results[:config.MAX_SEARCH_RESULTS]:
                title = res.get("title", "").strip()
                raw = res.get("raw_content", "") or res.get("content", "")
                if not raw: continue
                clean = _clean_tavily_content(raw)
                if not clean or len(clean) < 50: continue
                snippet = clean[:config.MAX_LINK_CONTENT_SIZE]
                parts.append(f"• {title}: {snippet}")
            return "\n".join(parts) if parts else ""
    return ""

@retry_async()
async def fetch_chainbase(keyword: str) -> str:
    url = "https://api.chainbase.com/tops/v1/tool/search-narrative-candidates"
    params = {"keyword": keyword}
    async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            logger.warning(f"[search] Chainbase fetch failed: status={r.status_code}")
            return ""
        data = r.json()
        items = data.get("data", data.get("items", []))
        if not isinstance(items, list): return ""
        seen = set()
        valid = []
        for item in items:
            kw = str(item.get("keyword") or item.get("narrative") or "").strip()
            sm = str(item.get("summary") or item.get("description") or "").strip()
            if not kw or not sm or not utils.is_english(sm): continue
            key = (kw.lower(), sm[:50].lower())
            if key in seen: continue
            seen.add(key)
            valid.append((kw, sm))
            if len(valid) >= config.MAX_SEARCH_RESULTS: break
        if not valid: return ""
        return "\n".join(f"{kw}: {sm}" for kw, sm in valid)

@retry_async()
async def fetch_mentions(keyword: str) -> str:
    if not keyword: return ""
    keywords_to_try = [keyword]
    if not keyword.startswith("$"):
        keywords_to_try.append(f"${keyword}")
    all_mentions = []
    seen_ids = set()
    async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as client:
        for kw in keywords_to_try:
            try:
                url = "https://api.chainbase.com/tops/v1/tool/search-mentions"
                params = {"keyword": kw}
                r = await client.get(url, params=params)
                if r.status_code != 200:
                    logger.warning(f"[search] Mentions failed for {kw}: {r.status_code}")
                    continue
                data = r.json()
                items = data.get("items", [])
                for item in items[:5]:
                    item_id = item.get("id")
                    if item_id in seen_ids: continue
                    seen_ids.add(item_id)
                    user = item.get("user", {})
                    username = user.get("screen_name", "unknown")
                    text = item.get("text", "")
                    if not text or len(text) < 20: continue
                    clean_text = text.replace("\n", " ").strip()
                    if len(clean_text) > 280:
                        clean_text = clean_text[:277] + "..."
                    all_mentions.append(f"@{username}: {clean_text}")
            except Exception as e:
                logger.warning(f"[search] Mentions error for {kw}: {e}")
                continue
    if not all_mentions: return ""
    return "Recent mentions:\n" + "\n\n".join(all_mentions[:5])
