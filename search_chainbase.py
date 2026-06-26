import httpx
import logging
import config
import utils
from retry import retry_async

logger = logging.getLogger(__name__)

@retry_async()
async def fetch_trends() -> list:
    async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as c:
        r = await c.get("https://api.chainbase.com/tops/v1/tool/list-trending-topics", params={"language": "en"})
        if r.status_code != 200: return []
        items = [t for t in r.json().get("items", []) if utils.is_english(t.get("summary", ""))]
        return sorted(items, key=lambda x: x.get("current_rank", 999))[:10]

@retry_async()
async def fetch_chainbase(keyword: str) -> str:
    async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as c:
        try:
            r = await c.get("https://api.chainbase.com/tops/v1/tool/search-narrative-candidates", params={"keyword": keyword})
            if r.status_code == 200:
                items = r.json().get("data", r.json().get("items", []))
                if isinstance(items, list) and items:
                    seen, valid = set(), []
                    for i in items:
                        kw = str(i.get("keyword") or i.get("narrative") or "").strip()
                        sm = str(i.get("summary") or i.get("description") or "").strip()
                        if not kw or not sm or not utils.is_english(sm): continue
                        key = (kw.lower(), sm[:50].lower())
                        if key in seen: continue
                        seen.add(key)
                        valid.append((kw, sm))
                        if len(valid) >= config.MAX_SEARCH_RESULTS: break
                    if valid:
                        return "\n".join(f"{kw}: {sm}" for kw, sm in valid)
        except Exception as e:
            logger.warning(f"[search] Narrative search error: {e}")
            
        try:
            r = await c.get("https://api.chainbase.com/tops/v1/tool/search-mentions", params={"keyword": keyword})
            if r.status_code == 200:
                items = r.json().get("items", [])
                mentions, seen_ids = [], set()
                for i in items[:5]:
                    if i.get("id") in seen_ids: continue
                    seen_ids.add(i["id"])
                    txt = i.get("text", "").replace("\n", " ").strip()
                    if len(txt) < 20: continue
                    mentions.append(f"@{i.get('user', {}).get('screen_name', 'unknown')}: {txt[:277] + '...' if len(txt) > 280 else txt}")
                if mentions:
                    return "Recent mentions:\n" + "\n".join(mentions)
        except Exception as e:
            logger.warning(f"[search] Mentions fallback error: {e}")
    return ""