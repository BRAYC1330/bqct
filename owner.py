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
async def _fetch_link_content(url: str, client) -> str:
    try:
        content = await bsky._fetch_url_content(client, url)
        if content:
            return content[:1000]
    except Exception as e:
        logger.warning(f"[owner] Link fetch failed {url}: {e}")
    return ""
async def _extract_embed_text(embed: dict, client) -> str:
    if not embed:
        return ""
    parts = []
    etype = embed.get("$type", "")
    if etype == "app.bsky.embed.record":
        rec = embed.get("record", {}).get("value", {})
        if rec and rec.get("text"):
            parts.append(rec["text"])
    elif etype == "app.bsky.embed.recordWithMedia":
        rec = embed.get("record", {}).get("value", {})
        if rec and rec.get("text"):
            parts.append(rec["text"])
    urls = re.findall(r'https?://\S+', " ".join(parts))
    for u in list(set(urls))[:2]:
        lc = await _fetch_link_content(u, client)
        if lc:
            parts.append(lc)
    return "\n".join(parts)
async def prepare(client, llm, task) -> List[Dict[str, Any]]:
    uri = task["uri"]
    user_text = task["text"]
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return []
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("cid", "")
    if not parent_cid:
        return []
    posts = chain.get("chain", [])
    context_parts = []
    for post in posts:
        rec = post.get("record", {})
        text = utils.clean_for_llm(rec.get("text", ""))
        embed = rec.get("embed")
        embed_text = await _extract_embed_text(embed, client)
        urls_in_text = re.findall(r'https?://\S+', text)
        link_texts = []
        for u in list(set(urls_in_text))[:2]:
            lc = await _fetch_link_content(u, client)
            if lc:
                link_texts.append(lc)
        entry = text
        if embed_text:
            entry += f"\n[EMBEDDED CONTENT]\n{embed_text}"
        if link_texts:
            entry += f"\n[LINK CONTENT]\n" + "\n---\n".join(link_texts)
        context_parts.append(entry)
    full_context = "\n\n".join(context_parts)
    last_three = context_parts[-3:] if len(context_parts) >= 3 else context_parts
    recent_context = "\n\n".join(last_three)
    clean_query = utils.clean_for_llm(user_text)
    search_data = ""
    source = ""
    do_tavily = "!t" in user_text.lower()
    if do_tavily:
        clean_text = re.sub(r'!t', '', user_text, flags=re.I).strip()
        q, t = generator.extract_search_intent(llm, clean_text)
        if q:
            snippet = full_context[:300]
            enriched = f"{q} in context: {snippet}"
            search_data = await search.fetch_tavily(enriched, t)
            source = "tavily"
    sig = build_content._get_signature(source, bool(search_data))
    max_reply_chars = config.MAX_COMMENT_CHARS - len(sig) - 10
    model_ctx = f"[FULL THREAD CONTEXT]\n{full_context}\n\n[RECENT COMMENTS]\n{recent_context}\n\n[USER QUERY]\n{clean_query}"
    if search_data:
        clean_search = utils.clean_for_llm(search_data)
        model_ctx += f"\n\n[SEARCH RESULTS]\n{clean_search}"
    if config.RAW_DEBUG:
        logger.info("=== [OWNER CONTEXT] ===")
        logger.info(model_ctx)
        logger.info("=== [END CONTEXT] ===")
    reply = generator.get_answer(llm, model_ctx, clean_query, max_chars=max_reply_chars, temperature=0.5, prompt_key="owner_reply")
    if not reply or not isinstance(reply, str):
        logger.warning("[owner] LLM returned empty reply")
        return []
    reply = reply.strip()
    if reply.startswith("```") and reply.endswith("```"):
        reply = reply[3:-3].strip()
    reply, facets_list = facets.enhance_tickers(reply)
    final_text = reply + sig
    if utils.count_graphemes(final_text) > config.MAX_COMMENT_CHARS:
        reply = utils.truncate_text(reply, config.MAX_COMMENT_CHARS, sig)
        if not reply or not isinstance(reply, str):
            return []
        reply, facets_list = facets.enhance_tickers(reply)
        final_text = reply + sig
    if config.RAW_DEBUG:
        logger.info("=== [FINAL POST] ===")
        logger.info(final_text)
        logger.info("=== [END POST] ===")
    return [{
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
    }]
