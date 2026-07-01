import logging
import re
import config
import bsky
import generator
from search_tavily import fetch_tavily
from search_chainbase import fetch_chainbase
import utils
import facets
import build_content
from models import Task
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


async def _fetch_link_content(url: str, client) -> str:
    try:
        logger.info(f"[owner] Fetching link content: {url}")
        content = await bsky.fetch_url_content(client, url)
        if content:
            logger.info(f"[owner] Fetched {len(content)} chars from {url}")
            return content[:1000]
        logger.warning(f"[owner] Empty content from {url}, trying Tavily extract")
        tavily_content = await fetch_tavily(f"site:{url}", "")
        if tavily_content:
            logger.info(f"[owner] Tavily extracted {len(tavily_content)} chars for {url}")
            return tavily_content[:1000]
    except Exception as e:
        logger.warning(f"[owner] Link fetch failed {url}: {e}")
    return ""


def _extract_urls_from_post(record: dict) -> list:
    urls = []
    seen = set()
    
    embed = record.get("embed", {})
    etype = embed.get("$type", "")
    logger.info(f"[owner] Post embed type: {etype}")
    
    post_facets = record.get("facets", [])
    logger.info(f"[owner] Post has {len(post_facets)} facets")
    for facet in post_facets:
        features = facet.get("features", [])
        for f in features:
            ftype = f.get("$type", "")
            logger.info(f"[owner] Facet feature type: {ftype}")
            if ftype == "app.bsky.richtext.facet#link":
                uri = f.get("uri", "")
                if uri.startswith("http") and uri not in seen:
                    seen.add(uri)
                    urls.append(uri)
    
    if etype == "app.bsky.embed.external":
        ext_uri = embed.get("external", {}).get("uri", "")
        logger.info(f"[owner] Embed external URI: {ext_uri}")
        if ext_uri.startswith("http") and ext_uri not in seen:
            seen.add(ext_uri)
            urls.append(ext_uri)
    elif etype == "app.bsky.embed.recordWithMedia":
        media = embed.get("media", {})
        if media.get("$type") == "app.bsky.embed.external":
            ext_uri = media.get("external", {}).get("uri", "")
            logger.info(f"[owner] RecordWithMedia external URI: {ext_uri}")
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


def _clean_operators(text: str) -> str:
    cleaned = re.sub(r'!\s*t\b', '', text, flags=re.I)
    cleaned = re.sub(r'!\s*c\b', '', cleaned, flags=re.I)
    return cleaned.strip()


async def prepare(client, llm, task: Task) -> List[Dict[str, Any]]:
    uri = task.uri
    user_text = task.text
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain:
        return []
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("cid", "")
    if not parent_cid:
        return []
    posts = chain.get("chain", [])
    logger.info(f"[owner] Thread chain has {len(posts)} posts")
    
    context_parts = []
    for i, post in enumerate(posts):
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
        logger.info(f"[owner] Processed post #{i+1}: text={len(text)} chars, embed={len(embed_text)} chars, links={len(link_texts)}")
    
    full_context = "\n\n".join(context_parts)
    last_three = context_parts[-3:] if len(context_parts) >= 3 else context_parts
    recent_context = "\n\n".join(last_three)
    clean_query = utils.clean_for_llm(_clean_operators(user_text))

    search_data = ""
    source = ""

    do_tavily = bool(re.search(r'!\s*t\b', user_text, re.I))
    do_chainbase = bool(re.search(r'!\s*c\b', user_text, re.I))
    logger.info(f"[owner] Operators: do_tavily={do_tavily}, do_chainbase={do_chainbase}")

    if do_tavily:
        q, t = generator.extract_search_intent(llm, clean_query, full_context)
        if q:
            logger.info(f"[owner] Generated search query: '{q}'")
            search_data = await fetch_tavily(q, t)
            if search_data:
                source = "tavily"
                logger.info(f"[owner] Tavily returned {len(search_data)} chars")
            else:
                logger.info("[owner] Tavily returned empty, falling back to Chainbase")
                kw = generator.extract_chainbase_keyword(llm, clean_query, recent_context)
                if kw:
                    search_data = await fetch_chainbase(kw)
                    if search_data:
                        sample = "\n".join(search_data.split("\n")[:6])
                        if generator.validate_search_results(llm, clean_query, sample):
                            source = "chainbase"
                        else:
                            search_data = ""

    elif do_chainbase:
        original_keyword = generator.extract_chainbase_keyword(llm, clean_query, recent_context)
        kw = original_keyword
        tried_keywords = set()
        for attempt in range(3):
            if kw:
                tried_keywords.add(kw.lower())
            logger.info(f"[owner] Chainbase attempt {attempt+1}: keyword='{kw or 'REGENERATING'}'")
            if not kw:
                tried_str = ", ".join(tried_keywords) if tried_keywords else "none"
                kw = generator.regenerate_keyword(llm, original_keyword, clean_query, recent_context, tried_keywords=tried_str)
                if not kw:
                    logger.info(f"[owner] Cannot regenerate keyword (attempt {attempt+1})")
                    break
                if kw.lower() in tried_keywords:
                    logger.info(f"[owner] Regenerated keyword '{kw}' was already tried, skipping")
                    kw = ""
                    continue
                logger.info(f"[owner] Regenerated keyword: '{kw}'")
                tried_keywords.add(kw.lower())
            search_data = await fetch_chainbase(kw)
            if search_data:
                logger.info(f"[owner] Fetched {len(search_data.split(chr(10)))} results for '{kw}'")
                sample = "\n".join(search_data.split("\n")[:6])
                if generator.validate_search_results(llm, clean_query, sample):
                    logger.info(f"[owner] Validation passed for '{kw}' ✓")
                    break
                logger.info(f"[owner] Validation failed for '{kw}' (irrelevant), retrying...")
                search_data = ""
            else:
                logger.info(f"[owner] No results for '{kw}'")
            kw = ""
        if not search_data:
            logger.info(f"[owner] All 3 attempts failed, proceeding without Chainbase data")
        if search_data:
            source = "chainbase"

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
