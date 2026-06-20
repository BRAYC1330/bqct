import logging
import config
import bsky
import generator
import utils
import facets
import build_content
from typing import List, Dict, Any, Tuple
logger = logging.getLogger(__name__)


def _normalize_handle(handle: str) -> str:
    return handle.lstrip("@").strip().lower()


async def run(client, llm, state) -> Tuple[List[Dict[str, Any]], dict]:
    actions = []
    greeted = set(state.scout_greeted or [])
    new_greeted = list(greeted)

    for raw_handle in config.SCOUT_HANDLES:
        handle = _normalize_handle(raw_handle)
        if handle in greeted:
            continue
        try:
            profile = await bsky.get_profile(client, handle)
            if not profile:
                logger.info(f"[scout] {handle} not on Bluesky yet")
                continue

            display_name = profile.get("displayName", handle)
            description = profile.get("description", "")
            logger.info(f"[scout] Found: @{handle} ({display_name})")

            prompt_ctx = f"Handle: @{handle}\nDisplay name: {display_name}\nBio: {description}"
            reply = generator.get_answer(
                llm,
                prompt_ctx,
                "Write a unique welcome post for this project joining Bluesky.",
                max_chars=config.MAX_COMMENT_CHARS - len(build_content.SIG_DEFAULT) - 10,
                temperature=0.8,
                prompt_key="scout_welcome",
                handle=handle
            )
            if not reply or not isinstance(reply, str):
                logger.warning(f"[scout] Empty greeting for {handle}")
                continue

            reply = reply.strip()
            reply, facets_list = facets.enhance_tickers(reply)
            final_text = reply + build_content.SIG_DEFAULT

            if utils.count_graphemes(final_text) > config.MAX_COMMENT_CHARS:
                reply = utils.truncate_text(reply, config.MAX_COMMENT_CHARS, build_content.SIG_DEFAULT)
                reply, facets_list = facets.enhance_tickers(reply)
                final_text = reply + build_content.SIG_DEFAULT

            actions.append({
                "type": "post_root",
                "args": {
                    "bot_did": config.BOT_DID,
                    "text": final_text,
                    "facets": facets_list
                }
            })
            new_greeted.append(handle)
            logger.info(f"[scout] Queued welcome for @{handle}")
        except Exception as e:
            logger.info(f"[scout] {handle} not found or error: {e}")

    state_update = {"scout_greeted": new_greeted}
    return actions, state_update
