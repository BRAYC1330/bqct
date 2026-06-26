import logging
import asyncio
import config
import bsky
import generator
from search_chainbase import fetch_chainbase
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
    clean_query = utils.clean_for_llm(user_text)
    
    classification = await generator.classify_community_input(llm, user_text, clean_root, clean_query)
    sentiment = classification["sentiment"]
    intent = classification["intent"]
    original_keyword = classification["keyword"]
    
    search_data = ""
    source = ""
    kw = original_keyword
    tried_keywords = set()
    
    if intent != "CASUAL":
        for attempt in range(3):
            if kw: tried_keywords.add(kw.lower())
            regen_task = None
            search_task = None
            
            if not kw:
                tried_str = ", ".join(tried_keywords) if tried_keywords else "none"
                regen_task = asyncio.create_task(generator.regenerate_keyword(llm, original_keyword, clean_query, clean_root, tried_keywords=tried_str))
            if kw:
                search_task = asyncio.create_task(fetch_chainbase(kw))
                
            if regen_task:
                kw = await regen_task
                if not kw: break
                if kw.lower() in tried_keywords:
                    kw = ""
                    continue
                tried_keywords.add(kw.lower())
                search_task = asyncio.create_task(fetch_chainbase(kw))
                
            if search_task:
                search_data = await search_task
                if search_data:
                    sample = "\n".join(search_data.split("\n")[:6])
                    if await generator.validate_search_results(llm, clean_query, sample):
                        break
                    search_data = ""
                else:
                    kw = ""
                    
    if intent == "CASUAL":
        sig = build_content.SIG_DEFAULT
    else:
        sig = build_content.SIG_CHAINBASE if search_data else build_content.SIG_DEFAULT
        
    max_reply_chars = config.MAX_COMMENT_CHARS - len(sig) - 10
    
    if intent == "CASUAL":
        ctx_text = f"[ROOT]\n{clean_root}"
        reply = await generator.get_answer(llm, ctx_text, user_text, max_chars=max_reply_chars, temperature=config.LLM_TEMP_CASUAL, prompt_key="casual_reply")
    elif not search_data:
        ctx_text = f"[ROOT]\n{clean_root}"
        reply = await generator.get_answer(llm, ctx_text, clean_query, max_chars=max_reply_chars, temperature=config.LLM_TEMP_STANDARD, prompt_key="dyor_fallback", keyword=original_keyword or "this topic")
    else:
        clean_search = utils.clean_for_llm(search_data)
        minimal_ctx = f"[ROOT]\n{clean_root}\n{clean_search}"
        reply = await generator.get_answer(llm, minimal_ctx, clean_query, max_chars=max_reply_chars, temperature=config.LLM_TEMP_STANDARD, prompt_key="community_reply")
        
    if not reply or not isinstance(reply, str): return []
    reply = reply.strip()
    
    if utils.count_graphemes(reply + sig) > config.MAX_COMMENT_CHARS:
        reply = utils.truncate_text(reply, config.MAX_COMMENT_CHARS, sig)
    if not reply or not isinstance(reply, str): return []
    
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