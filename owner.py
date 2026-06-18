import logging
import re
import config
import bsky
import generator
from search_tavily import fetch_tavily
import utils
import facets
import build_content
from typing import List, Dict, Any
logger = logging.getLogger(__name__)
async def _fetch_link_content(url: str, client) -> str:
    try:
        logger.info(f"[owner] Fetching link content: {url}")
        content = await bsky._fetch_url_content(client, url)
        if content:
            logger.info(f"[owner] Fetched {len(content)} chars from {url}")
            return content[:1000]
        logger.warning(f"[owner] Empty content from {url}")
    except Exception as e:
        logger.warning(f"[owner] Link fetch failed {url}: {e}")
    return ""
def _extract_urls_from_post(record: dict) -> list:
    urls = []
    seen = set()
    post_facets = record.get("facets", [])
    for facet in post_facets:
        features = facet.get("features", [])
        for f in features:
            if f.get("$type") == "app.bsky.richtext.facet#link":
                uri = f.get("uri", "")
                if uri.startswith("http") and uri not in seen:
                    seen.add(uri)
                    urls.append(uri)
    embed = record.get("embed", {})
    etype = embed.get("$type", "")
    if etype == "app.bsky.embed.external":
        ext_uri = embed.get("external", {}).get("uri", "")
        if ext_uri.startswith("http") and ext_uri not in seen:
            seen.add(ext_uri)
            urls.append(ext_uri)
    elif etype == "app.bsky.embed.recordWithMedia":
        media = embed.get("media", {})
        if media.get("$type") == "app.bsky.embed.external":
            ext_uri = media.get("external", {}).get("uri", "")
            if ext_uri.startswith("http") and ext_uri not in seen:
                seen.add(ext_uri)
                urls.append(ext_uri)
    raw_text = record.get("text", "")
    for u in re.findall(r'https?://\S+', raw_text):
        clean_u = u.rstrip('.,;:)')
        if clean_u not in seen:
            seen.add(clean_u)
            urls.append(clean_u)
    logger.info(f"[owner] Extracted URLs from post: {urls}")
    return urls[:3]
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
    if etype == "app.bsky.embed.external":
        ext = embed.get("external", {})
        title = ext.get("title", "")
        desc = ext.get("description", "")
        if title or desc:
            parts.append(f"{title}: {desc}".strip())
    elif etype == "app.bsky.embed.recordWithMedia":
        media = embed.get("media", {})
        if media.get("$type") == "app.bsky.embed.external":
            ext = media.get("external", {})
            title = ext.get("title", "")
            desc = ext.get("description", "")
            if title or desc:
                parts.append(f"{title}: {desc}".strip())
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
        urls = _extract_urls_from_post(rec)
        link_texts = []
        for u in urls:
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
            search_data = await fetch_tavily(enriched, t)
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
