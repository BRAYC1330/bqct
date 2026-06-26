import logging
import config
import bsky
import generator
import utils
import facets
import build_content
from models import Task
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def prepare(client, llm, task: Task) -> List[Dict[str, Any]]:
    handle = task.text
    profile = await bsky.get_profile(client, handle)
    if not profile:
        return []

    display_name = profile.get("displayName", handle)
    description = profile.get("description", "")
    prompt_ctx = f"Handle: @{handle}\nDisplay name: {display_name}\nBio: {description}"
    
    reply = await generator.get_answer(
        llm, prompt_ctx, "Write a unique welcome post.",
        max_chars=config.MAX_COMMENT_CHARS - len(build_content.SIG_DEFAULT) - 10,
        temperature=0.8, prompt_key="scout_welcome", handle=handle
    )
    
    if not reply or not isinstance(reply, str):
        return []
        
    reply = reply.strip()
    reply, facets_list = facets.enhance_tickers(reply)
    final_text = reply + build_content.SIG_DEFAULT
    
    if utils.count_graphemes(final_text) > config.MAX_COMMENT_CHARS:
        reply = utils.truncate_text(reply, config.MAX_COMMENT_CHARS, build_content.SIG_DEFAULT)
        reply, facets_list = facets.enhance_tickers(reply)
        final_text = reply + build_content.SIG_DEFAULT

    return [
        {
            "type": "post_root",
            "args": {
                "bot_did": config.BOT_DID,
                "text": final_text,
                "facets": facets_list
            }
        },
        {
            "type": "track_scout",
            "args": {"handle": handle}
        }
    ]