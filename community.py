import logging
import config
import bsky
import generator
from search_chainbase import fetch_chainbase_validated
import utils
import facets
import build_content
from models import RunContext, Task
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def prepare(ctx: RunContext, client, llm, task: Task) -> List[Dict[str, Any]]:
    actions = []
    uri = task.uri
    user_text = task.text
    parent_uri = task.parent_uri or ""
    
    if not parent_uri: return []
    
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return []
    
    root_uri = chain.get("root_uri", parent_uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("cid", "")
    if not parent_cid: return []
    
    root_text = chain.get("root_text", "")
    clean_root = utils.clean_for_llm(root_text)
    
    sentiment = generator.classify_sentiment(llm, user_text, clean_root)
    clean_query = utils.clean_for_llm(user_text)
    intent = generator.classify_intent(llm, user_text, clean_root)
    
    search_data = ""
    original_keyword = ""
    
    if intent != "CASUAL":
        original_keyword = generator.extract_chainbase_keyword(llm, clean_query, clean_root)
        search_data = await fetch_chainbase_validated(llm, clean_query, clean_root, original_keyword)
        if search_data:
            logger.info(f"[search] Fetched data for '{original_keyword}'")

    sig = build_content.SIG_DEFAULT
    if intent != "CASUAL" and search_data:
        sig = build_content.SIG_CHAINBASE
        
    max_reply_chars = config.MAX_COMMENT_CHARS - len(sig) - 10
    
    if intent == "CASUAL":
        ctx_text = f"{config.CTX_ROOT_POST}\n{clean_root}"
        reply = generator.get_answer(llm, ctx_text, user_text, max_chars=max_reply_chars, temperature=config.LLM_TEMP_CASUAL, prompt_key="casual_reply")
    elif not search_data:
        ctx_text = f"{config.CTX_ROOT_POST}\n{clean_root}"
        reply = generator.get_answer(llm, ctx_text, clean_query, max_chars=max_reply_chars, temperature=config.LLM_TEMP_STANDARD, prompt_key="dyor_fallback", keyword=original_keyword or "this topic")
    else:
        clean_search = utils.clean_for_llm(search_data)
        minimal_ctx = f"{config.CTX_ROOT_POST}\n{clean_root}\n{config.CTX_SEARCH_RESULTS}\n{clean_search}"
        reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_reply_chars, temperature=config.LLM_TEMP_STANDARD, prompt_key="community_reply")

    if config.RAW_DEBUG:
        logger.info("=== [COMMUNITY DEBUG] ===")
        logger.info(f"Intent: {intent} | Keyword: {original_keyword} | Search: {'yes' if search_data else 'no'} | Sig: {sig}")
        logger.info(f"Raw Model Output: {reply}")
        logger.info("=== [END DEBUG] ===")

    if not reply or not isinstance(reply, str):
        logger.warning("[community] LLM returned empty reply")
        return []
        
    reply = reply.strip()
    reply, facets_list = facets.enhance_tickers(reply)
    final_text = reply + sig
    
    if utils.count_graphemes(final_text) > config.MAX_COMMENT_CHARS:
        reply = utils.truncate_text(reply, config.MAX_COMMENT_CHARS, sig)
        if not reply or not isinstance(reply, str):
            return []
        reply, facets_list = facets.enhance_tickers(reply)
        final_text = reply + sig

    actions.append({
        "type": "post_reply",
        "args": {
            "bot_did": config.BOT_DID, 
            "text": final_text, 
            "root_uri": root_uri, 
            "root_cid": root_cid, 
            "parent_uri": uri, 
            "parent_cid": parent_cid, 
            "facets": facets_list
        }
    })
    
    if ctx.like(uri):
        actions.append({"type": "post_like", "args": {"bot_did": config.BOT_DID, "subject_uri": uri, "subject_cid": parent_cid}})
    elif sentiment == "POSITIVE" and ctx.try_casual_like(uri):
        actions.append({"type": "post_like", "args": {"bot_did": config.BOT_DID, "subject_uri": uri, "subject_cid": parent_cid}})
        
    return actions
