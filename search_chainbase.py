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
        try:
            r = await c.get("https://api.chainbase.com/tops/v1/tool/search-narrative-candidates", params={"keyword": keyword})
            if r.status_code == 200:
                items = r.json().get("data", r.json().get("items", []))
                if isinstance(items, list) and items:
                    seen, valid = set(), []
                    for i in items:
                        kw = str(i.get("keyword") or i.get("narrative") or "").strip()
                        sm = str(i.get("summary") or i.get("description") or "").strip()
                        if not kw or not sm or not utils.is_english(sm):
                            continue
                        key = (kw.lower(), sm[:50].lower())
                        if key in seen:
                            continue
                        seen.add(key)
                        valid.append((kw, sm))
                        if len(valid) >= config.MAX_SEARCH_RESULTS:
                            break
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
                    if i.get("id") in seen_ids:
                        continue
                    seen_ids.add(i["id"])
                    txt = i.get("text", "").replace("\n", " ").strip()
                    if len(txt) < 20:
                        continue
                    mentions.append(f"@{i.get('user', {}).get('screen_name', 'unknown')}: {txt[:277] + '...' if len(txt) > 280 else txt}")
                if mentions:
                    return "Recent mentions:\n" + "\n".join(mentions)
        except Exception as e:
            logger.warning(f"[search] Mentions fallback error: {e}")
        return ""

async def fetch_chainbase_validated(llm, query: str, context: str, initial_keyword: str = "") -> str:
    """
    Unified search logic with retry, keyword regeneration and validation.
    Replaces duplicated loops in community.py and owner.py.
    """
    import generator
    
    kw = initial_keyword
    tried_keywords = set()
    search_data = ""

    for attempt in range(3):
        if kw:
            tried_keywords.add(kw.lower())
            logger.info(f"[search] Attempt {attempt+1}: keyword='{kw}'")
            search_data = await fetch_chainbase(kw)

            if search_data:
                sample = "\n".join(search_data.split("\n")[:6])
                if generator.validate_search_results(llm, query, sample):
                    logger.info(f"[search] Validation passed for '{kw}' ✅")
                    break
                logger.info(f"[search] Validation failed for '{kw}' (irrelevant), retrying...")
                search_data = ""
            else:
                logger.info(f"[search] No results for '{kw}'")
                kw = ""

        tried_str = ", ".join(tried_keywords) if tried_keywords else "none"
        kw = generator.regenerate_keyword(llm, initial_keyword, query, context, tried_keywords=tried_str)
        
        if not kw:
            logger.info(f"[search] Cannot regenerate keyword (attempt {attempt+1})")
            break
        if kw.lower() in tried_keywords:
            logger.info(f"[search] Regenerated keyword '{kw}' was already tried, skipping")
            kw = ""
            continue

    return search_data
