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
        if r.status_code != 200:
            return []
        items = [t for t in r.json().get("items", []) if utils.is_english(t.get("summary", ""))]
        return sorted(items, key=lambda x: x.get("current_rank", 999))[:10]

@retry_async()
async def fetch_chainbase(keyword: str) -> str:
    async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as c:
        r = await c.get("https://api.chainbase.com/tops/v1/tool/search-narrative-candidates", params={"keyword": keyword})
        if r.status_code != 200:
            return ""
        items = r.json().get("data", r.json().get("items", []))
        if not isinstance(items, list):
            return ""
        seen, valid = set(), []
        for i in items:
            kw, sm = str(i.get("keyword") or "").strip(), str(i.get("summary") or "").strip()
            if not kw or not sm or not utils.is_english(sm):
                continue
            key = (kw.lower(), sm[:50].lower())
            if key in seen:
                continue
            seen.add(key)
            valid.append((kw, sm))
            if len(valid) >= config.MAX_SEARCH_RESULTS:
                break
        return "\n".join(f"{kw}: {sm}" for kw, sm in valid) if valid else ""

@retry_async()
async def fetch_mentions(keyword: str) -> str:
    if not keyword:
        return ""
    kw_list = [keyword, f"${keyword}"] if not keyword.startswith("$") else [keyword]
    mentions, seen_ids = [], set()
    async with httpx.AsyncClient(timeout=config.SEARCH_TIMEOUT) as c:
        for kw in kw_list:
            try:
                r = await c.get("https://api.chainbase.com/tops/v1/tool/search-mentions", params={"keyword": kw})
                if r.status_code != 200:
                    continue
                for i in r.json().get("items", [])[:5]:
                    if i.get("id") in seen_ids:
                        continue
                    seen_ids.add(i["id"])
                    txt = i.get("text", "").replace("\n", " ").strip()
                    if len(txt) < 20:
                        continue
                    mentions.append(f"@{i.get('user', {}).get('screen_name', 'unknown')}: {txt[:277] + '...' if len(txt) > 280 else txt}")
            except Exception:
                pass
    return f"Recent mentions:\n" + "\n".join(mentions[:5]) if mentions else ""