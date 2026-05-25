import logging, config
from typing import List, Dict

logger = logging.getLogger(__name__)

async def get_trending_topics_raw() -> List[Dict]:
    if not config.SEARCH_CHAINBASE_ENABLED: return []
    from search_chainbase import fetch_trends
    return await fetch_trends()

async def fetch_chainbase(keyword: str) -> str:
    if not config.SEARCH_CHAINBASE_ENABLED: return ""
    from search_chainbase import fetch_chainbase as _fn
    return await _fn(keyword)

async def fetch_mentions(keyword: str) -> str:
    if not config.SEARCH_CHAINBASE_ENABLED: return ""
    from search_chainbase import fetch_mentions as _fn
    return await _fn(keyword)

async def fetch_tavily(query: str, time_range: str = "") -> str:
    if not config.SEARCH_TAVILY_ENABLED: return ""
    from search_tavily import fetch_tavily as _fn
    return await _fn(query, time_range)
