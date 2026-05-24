import logging
import config
import utils
import facets
import build_content
from typing import Optional, Tuple, Dict, Any
logger = logging.getLogger(__name__)
async def prepare(llm, task_type: str, client=None) -> Optional[Dict[str, Any]]:
    trends = await _fetch_trends()
    if not trends:
        logger.warning(f"[digest] No trends fetched")
        return None
    final_post, embed = await build_content.build_digest(llm, trends, task_type, client=client)
    if not final_post:
        logger.warning(f"[digest] build_digest returned None")
        return None
    final_post = final_post.strip()
    logger.info(f"[TOKENS] {utils.count_tokens(final_post, llm)} / {config.MODEL_N_CTX}")
    facets_list = facets.generate_digest_facets(final_post)
    action = {
        "type": "post_root",
        "args": {"bot_did": config.BOT_DID, "text": final_post, "facets": facets_list},
        "track_uri": True
    }
    if embed:
        action["args"]["embed"] = embed
    return action
async def _fetch_trends():
    import search
    return await search.get_trending_topics_raw()
