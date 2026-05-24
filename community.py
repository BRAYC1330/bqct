import logging
import config
import bsky
import generator
import search
import utils
import facets
import build_content
from models import RunContext
from typing import List, Dict, Any
logger = logging.getLogger(__name__)
async def prepare(ctx: RunContext, client, llm, task) -> List[Dict[str, Any]]:
    actions = []
    uri = task["uri"]
    user_text = task["text"]
    parent_uri = task.get("parent_uri", "")
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
    original_keyword = generator.extract_chainbase_keyword(llm, clean_query, clean_root)

    search_data = ""
    kw = original_keyword
    tried_keywords = set()
    
    for attempt in range(3):
        if kw:
            tried_keywords.add(kw.lower())
        
        logger.info(f"[search] Attempt {attempt+1}: keyword='{kw or 'REGENERATING'}'")
        
        if not kw:
            kw = generator.regenerate_keyword(llm, original_keyword, clean_query, clean_root)
            if not kw:
                logger.info(f"[search] Cannot regenerate keyword (attempt {attempt+1})")
                break
            if kw.lower() in tried_keywords:
                logger.info(f"[search] Regenerated keyword '{kw}' was already tried, skipping")
                kw = ""
                continue
            logger.info(f"[search] Regenerated keyword: '{kw}'")
            tried_keywords.add(kw.lower())

        search_data = await search.fetch_chainbase(kw)
        if search_data:
            logger.info(f"[search] Fetched {len(search_data.split(chr(10)))} results for '{kw}'")
            sample = "\n".join(search_data.split("\n")[:3])
            if generator.validate_search_results(llm, clean_query, sample):
                logger.info(f"[search] Validation passed for '{kw}' ✓")
                break
            logger.info(f"[search] Validation failed for '{kw}' (irrelevant), retrying...")
            search_data = ""
        else:
            logger.info(f"[search] No results for '{kw}'")
        kw = ""
    
    if not search_data:
        logger.info(f"[search] All 3 attempts failed, proceeding without search data")

    if intent == "CASUAL":
        sig = build_content.SIG_DEFAULT
    else:
        sig = build_content.SIG_CHAINBASE if search_data else build_content.SIG_DEFAULT
    
    max_reply_chars = config.MAX_COMMENT_CHARS - len(sig) - 10
    if intent == "CASUAL":
        ctx_text = f"[ROOT]\n{clean_root}"
        reply = generator.get_answer(llm, ctx_text, user_text, max_chars=max_reply_chars, temperature=config.LLM_TEMP_CASUAL, prompt_key="casual_reply")
    elif not search_data:
        ctx_text = f"[ROOT]\n{clean_root}"
        reply = generator.get_answer(llm, ctx_text, clean_query, max_chars=max_reply_chars, temperature=config.LLM_TEMP_STANDARD, prompt_key="dyor_fallback", keyword=original_keyword or "this topic")
    else:
        clean_search = utils.clean_for_llm(search_data)
        minimal_ctx = f"[ROOT]\n{clean_root}\n\n{clean_search}"
        reply = generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_reply_chars, temperature=config.LLM_TEMP_STANDARD, prompt_key="community_reply")
    
    if config.RAW_DEBUG:
        logger.info("=== [COMMUNITY DEBUG] ===")
        logger.info(f"Intent: {intent} | Keyword: {original_keyword} | Search: {'yes' if search_data else 'no'} | Sig: {sig}")
        logger.info(f"Prompt Context:\n[ROOT]\n{clean_root}")
        if search_data:
            logger.info(f"[SEARCH]\n{utils.clean_for_llm(search_data)}")
        logger.info(f"Raw Model Output: {reply}")
        logger.info("=== [END DEBUG] ===")
    
    reply = reply.strip()
    reply, facets_list = facets.enhance_tickers(reply)
    final_text = reply + sig
    if utils.count_graphemes(final_text) > config.MAX_COMMENT_CHARS:
        reply = utils.truncate_text(reply, config.MAX_COMMENT_CHARS, sig)
        reply, facets_list = facets.enhance_tickers(reply)
        final_text = reply + sig
    
    actions.append({
        "type": "post_reply",
        "args": {"bot_did": config.BOT_DID, "text": final_text, "root_uri": root_uri, "root_cid": root_cid, "parent_uri": uri, "parent_cid": parent_cid, "facets": facets_list}
    })
    if ctx.like(uri):
        actions.append({"type": "post_like", "args": {"bot_did": config.BOT_DID, "subject_uri": uri, "subject_cid": parent_cid}})
    elif sentiment == "POSITIVE" and ctx.try_casual_like(uri):
        actions.append({"type": "post_like", "args": {"bot_did": config.BOT_DID, "subject_uri": uri, "subject_cid": parent_cid}})
    return actions
