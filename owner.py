import logging
import re
import config
import bsky
import generator
import search
import utils
import facets
import build_content
from typing import List, Dict, Any
logger = logging.getLogger(__name__)
async def extract_embed_context(embed: dict, client) -> str:
    if not embed: return ""
    parts = []
    etype = embed.get("$type", "")
    if etype == "app.bsky.embed.record":
        rec = embed.get("record", {}).get("value", {})
        if rec and rec.get("text"):
            parts.append(f"QUOTED TEXT: {rec['text']}")
    elif etype == "app.bsky.embed.images":
        for img in embed.get("images", []):
            if img.get("alt"): parts.append(f"IMAGE ALT: {img['alt']}")
    elif etype == "app.bsky.embed.recordWithMedia":
        rec = embed.get("record", {}).get("value", {})
        if rec and rec.get("text"): parts.append(f"QUOTED TEXT: {rec['text']}")
        media = embed.get("media", {})
        if media.get("$type") == "app.bsky.embed.external":
            ext = media.get("external", {})
            if ext.get("description"): parts.append(f"LINK DESC: {ext['description']}")
            if ext.get("title"): parts.append(f"LINK TITLE: {ext['title']}")
    elif etype == "app.bsky.embed.external":
        ext = embed.get("external", {})
        if ext.get("description"): parts.append(f"LINK DESC: {ext['description']}")
        if ext.get("title"): parts.append(f"LINK TITLE: {ext['title']}")
    urls = re.findall(r'https?://\S+', " ".join(parts))
    fetched = []
    for u in list(set(urls))[:2]:
        try:
            content = await bsky._fetch_url_content(client, u)
            if content: fetched.append(f"LINK CONTENT ({u}): {content[:config.MAX_LINK_CONTENT_SIZE]}")
        except: pass
    if parts: return "[EMBED]\n" + "\n".join(parts) + "\n" + "\n".join(fetched)
    return ""
async def prepare(client, llm, task) -> List[Dict[str, Any]]:
    uri = task["uri"]
    user_text = task["text"]
    embed = task.get("embed")
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return []
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_uri = uri
    parent_cid = chain.get("cid", "")
    if not parent_cid: return []
    root_record = chain.get("root_record", {})
    root_text_raw = root_record.get("text", "")
    if not root_text_raw:
        chain_posts = chain.get("chain", [])
        if chain_posts:
            first_post = chain_posts[0]
            first_record = first_post.get("record", {})
            root_text_raw = first_record.get("text", "")
            if not root_cid:
                root_cid = first_post.get("cid", "")
            if not root_uri:
                root_uri = first_post.get("uri", uri)
    root_embed = root_record.get("embed")
    root_text_clean = utils.clean_for_llm(root_text_raw)
    root_embed_context = await extract_embed_context(root_embed, client)
    root_context = root_text_clean
    if root_embed_context:
        root_context = f"{root_text_clean}\n{root_embed_context}"
    posts = chain.get("chain", [])
    history_lines = []
    for post in posts[1:]:
        rec = post.get("record", {})
        author = post.get("author", {})
        did = author.get("did", "")
        text = utils.clean_for_llm(rec.get("text", ""))
        if not text: continue
        if did == config.OWNER_DID: prefix = "OWNER:"
        elif did == config.BOT_DID: prefix = "BOT:"
        else: prefix = "USER:"
        history_lines.append(f"{prefix} {text}")
    history_block = "\n".join(history_lines[-5:]) if history_lines else "No history."
    clean_query = utils.clean_for_llm(user_text)
    search_data = ""
    source = ""
    do_search = "!t" in user_text.lower() or "!c" in user_text.lower()
    if do_search:
        clean_text = re.sub(r'(!t|!c)', '', user_text, flags=re.I).strip()
        topic_context = f"{root_context}\n{history_block}".strip()
        if "!c" in user_text.lower():
            kw = generator.extract_chainbase_keyword(llm, clean_text, topic_context)
            if kw:
                search_data = await search.fetch_chainbase(kw)
                source = "chainbase"
        else:
            q, t = generator.extract_search_intent(llm, clean_text)
            if q:
                if root_text_clean:
                    snippet = root_text_clean[:200]
                    enriched_query = f"{q} in context: {snippet}"
                else:
                    enriched_query = q
                if config.RAW_DEBUG:
                    logger.info(f"=== [SEARCH QUERY] ===")
                    logger.info(f"Original: {clean_text}")
                    logger.info(f"Extracted: {q} | Time: {t or 'none'}")
                    logger.info(f"Enriched: {enriched_query}")
                    logger.info("=== [END SEARCH QUERY] ===")
                search_data = await search.fetch_tavily(enriched_query, t)
                source = "tavily"
                if config.RAW_DEBUG and search_data:
                    logger.info(f"=== [SEARCH RAW RESULTS] ===")
                    logger.info(search_data[:1500] + ("..." if len(search_data) > 1500 else ""))
                    logger.info("=== [END SEARCH RESULTS] ===")
    clean_search = utils.clean_for_llm(search_data) if search_data else ""
    current_embed_context = await extract_embed_context(embed, client)
    model_ctx = (
        f"[QUERY]\n{clean_query}\n"
        f"[CONVERSATION]\n"
        f"[ROOT]\n{root_context}\n"
        f"[HISTORY]\n{history_block}\n"
        f"[SEARCH]\n{clean_search if clean_search else 'No external data'}\n"
        f"{current_embed_context}"
    )
    if config.RAW_DEBUG:
        logger.info("=== [OWNER CONTEXT] ===")
        logger.info(model_ctx)
        logger.info("=== [END CONTEXT] ===")
    sig = build_content._get_signature(source, bool(search_data))
    max_reply_chars = config.MAX_COMMENT_CHARS - len(sig) - 10
    try:
        reply = generator.get_answer(llm, model_ctx, clean_query, max_chars=max_reply_chars, temperature=0.5, prompt_key="owner_reply")
        if not reply or not isinstance(reply, str):
            logger.warning("[owner] LLM returned empty/non-string reply, using fallback")
            reply = "Interesting perspective. Let me think about this more deeply."
        reply = reply.strip()
        if reply.startswith("```") and reply.endswith("```"):
            reply = reply[3:-3].strip()
        reply, facets_list = facets.enhance_tickers(reply)
        final_text = reply + sig
        if utils.count_graphemes(final_text) > config.MAX_COMMENT_CHARS:
            reply = utils.truncate_text(reply, config.MAX_COMMENT_CHARS, sig)
            if not reply or not isinstance(reply, str):
                reply = "Interesting perspective. Let me think about this more deeply."
            reply, facets_list = facets.enhance_tickers(reply)
            final_text = reply + sig
    except Exception as e:
        logger.error(f"[owner] Reply generation failed: {type(e).__name__}: {repr(e)}")
        reply = "Interesting perspective. Let me think about this more deeply."
        reply, facets_list = facets.enhance_tickers(reply)
        final_text = reply + sig
    if config.RAW_DEBUG:
        logger.info("=== [FINAL POST] ===")
        logger.info(final_text)
        logger.info("=== [END POST] ===")
    return [{
        "type": "post_reply",
        "args": {"bot_did": config.BOT_DID, "text": final_text, "root_uri": root_uri, "root_cid": root_cid, "parent_uri": parent_uri, "parent_cid": parent_cid, "facets": facets_list}
    }]
