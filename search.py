import logging
import re
import config
import utils
from retry import retry_async
from typing import List, Dict
import httpx
logger = logging.getLogger(__name__)
def _clean_tavily_content(text: str) -> str:
    if not text: return ""
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[*_#~`>]', '', text)
    text = re.sub(r'\s*\n\s*', '\n', text)
    result = ' '.join(text.split())
    return result.strip()
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
        "include_answer": "basic",
        "search_depth": "basic",
        "max_results": config.MAX_SEARCH_RESULTS,
        "include_raw_content": "text",
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
            answer = data.get("answer", "")
            results = data.get("results", [])
            parts = []
            if answer:
                clean = _clean_tavily_content(answer)
                if clean: parts.append(f"[SUMMARY] {clean}")
            for res in results[:config.MAX_SEARCH_RESULTS]:
                title = res.get("title", "").strip()
                content = _clean_tavily_content(res.get("content", ""))
                if title and content:
                    parts.append(f"• {title}: {content}")
                elif content:
                    parts.append(f"• {content}")
            return "\n".join(parts)
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