import logging
import re
import config
import bsky
import generator
from search_tavily import fetch_tavily
from search_chainbase import fetch_chainbase_validated
import utils
import facets
import build_content
from models import Task
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def _strip_reply_prefix(text: str) -> str:
    prefixes = [
        r'^\s*</?\w+>?\s*', r'^\s*\[?ANSWER\]?\s*:?\s*', r'^\s*\[?RESPONSE\]?\s*:?\s*',
        r'^\s*\[?REPLY\]?\s*:?\s*', r'^\s*\[?MESSAGE\]?\s*:?\s*', r'^\s*Answer\s*:\s*',
        r'^\s*Response\s*:\s*', r'^\s*Reply\s*:\s*', r'^\s*Message\s*:\s*', r'^\s*A\s*:\s*', r'^\s*>\s*',
    ]
    cleaned = text
    for prefix in prefixes:
        cleaned = re.sub(prefix, '', cleaned, flags=re.I).strip()
    return cleaned

async def _fetch_link_content(url: str, client) -> str:
    try:
        logger.info(f"[owner] Fetching link content: {url}")
        content = await bsky.fetch_url_content(client, url)
        if content:
            logger.info(f"[owner] Fetched {len(content)} chars from {url}")
            return content[:600]
        logger.warning(f"[owner] Empty content from {url}, trying Tavily extract")
        tavily_content = await fetch_tavily(f"site:{url}", "")
        if tavily_content:
            logger.info(f"[owner] Tavily extracted {len(tavily_content)} chars for {url}")
            return tavily_content[:600]
    except Exception as e:
        logger.warning(f"[owner] Link fetch failed {url}: {e}")
    return ""

def _extract_urls_from_post(record: dict) -> list:
    urls = []
    seen = set()
    embed = record.get("embed", {})
    etype = embed.get("$type", "")
    
    post_facets = record.get("facets", [])
    for facet in post_facets:
        features = facet.get("features", [])
        for f in features:
            ftype = f.get("$type", "")
            if ftype == "app.bsky.richtext.facet#link":
                uri = f.get("uri", "")
                if uri.startswith("http") and uri not in seen:
                    seen.add(uri)
                    urls.append(uri)
                    
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
            
    return urls[:3]

async def _extract_embed_text(embed: dict, client) -> str:
    if not embed: return ""
    parts = []
    etype = embed.get("$type", "")
    
    if etype == "app.bsky.embed.record":
        rec = embed.get("record", {}).get("value", {})
        if rec and rec.get("text"): parts.append(rec["text"])
    elif etype == "app.bsky.embed.recordWithMedia":
        rec = embed.get("record", {}).get("value", {})
        if rec and rec.get("text"): parts.append(rec["text"])
        media = embed.get("media", {})
        if media.get("$type") == "app.bsky.embed.external":
            ext = media.get("external", {})
            title = ext.get("title", "")
            desc = ext.get("description", "")
            if title or desc: parts.append(f"{title}: {desc}".strip())
    elif etype == "app.bsky.embed.external":
        ext = embed.get("external", {})
        title = ext.get("title", "")
        desc = ext.get("description", "")
        if title or desc: parts.append(f"{title}: {desc}".strip())
        
    return "\n".join(parts)

def _clean_operators(text: str) -> str:
    cleaned = re.sub(r'!\s*t\b', '', text, flags=re.I)
    cleaned = re.sub(r'!\s*c\b', '', cleaned, flags=re.I)
    bot_handle = config.BOT_HANDLE.replace('@', '')
    cleaned = re.sub(rf'@\b{re.escape(bot_handle)}\b(\.\w+)?', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

async def prepare(client, llm, task: Task) -> List[Dict[str, Any]]:
    uri = task.uri
    user_text = task.text
    
    chain = await bsky.fetch_thread_chain(client, uri)
    if not chain: return []
    
    root_uri = chain.get("root_uri", uri)
    root_cid = chain.get("root_cid", "")
    parent_cid = chain.get("cid", "")
    if not parent_cid: return []
    
    posts = chain.get("chain", [])
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
            if lc: link_texts.append(lc)
            
        entry = text
        if embed_text:
            entry += f"\n{config.CTX_EMBED.format(embed_text)}"
        if link_texts:
            joined_links = "\n---\n".join(link_texts)
            entry += f"\n{config.CTX_LINKED_CONTENT.format(joined_links)}"
        context_parts.append(entry)

    root_post = context_parts[0] if context_parts else ""
    if len(context_parts) > 2:
        thread_posts = context_parts[1:-3] if len(context_parts) > 4 else context_parts[1:-1]
        thread_content = "\n".join(thread_posts) if thread_posts else "(no intermediate posts)"
    else:
        thread_content = "(no intermediate posts)"
        
    last_three = context_parts[-3:] if len(context_parts) >= 3 else context_parts
    recent_replies = "\n".join(last_three)
    
    clean_query = utils.clean_for_llm(_clean_operators(user_text))
    search_data = ""
    source = ""
    
    do_tavily = bool(re.search(r'!\s*t\b', user_text, re.I))
    do_chainbase = bool(re.search(r'!\s*c\b', user_text, re.I))
    
    if do_tavily:
        context_for_intent = f"{root_post}\n{thread_content}\n{recent_replies}"
        q, t = generator.extract_search_intent(llm, clean_query, context_for_intent)
        if q:
            search_data = await fetch_tavily(q, t)
            if search_data:
                source = "tavily"
            else:
                logger.info("[owner] Tavily empty, falling back to Chainbase")
                kw = generator.extract_chainbase_keyword(llm, clean_query, recent_replies)
                if kw:
                    search_data = await fetch_chainbase_validated(llm, clean_query, recent_replies, kw)
                    if search_data: source = "chainbase"
                    
    elif do_chainbase:
        original_keyword = generator.extract_chainbase_keyword(llm, clean_query, recent_replies)
        search_data = await fetch_chainbase_validated(llm, clean_query, recent_replies, original_keyword)
        if search_data: source = "chainbase"

    sig = build_content._get_signature(source, bool(search_data))
    max_reply_chars = config.MAX_COMMENT_CHARS - len(sig) - 10
    
    model_ctx = f"""{config.CTX_ROOT_POST}
{root_post}
{config.CTX_THREAD}
{thread_content}
{config.CTX_RECENT_REPLIES}
{recent_replies}
{config.CTX_CURRENT_QUERY}
{clean_query}"""

    if search_data:
        clean_search = utils.clean_for_llm(search_data)
        model_ctx += f"\n{config.CTX_SEARCH_RESULTS}\n{clean_search}"

    reply = generator.get_answer(llm, model_ctx, clean_query, max_chars=max_reply_chars, temperature=0.5, prompt_key="owner_reply")
    
    if not reply or not isinstance(reply, str):
        logger.warning("[owner] LLM returned empty reply")
        return []
        
    reply = reply.strip()
    reply = _strip_reply_prefix(reply)
    if reply.startswith("```") and reply.endswith("```"):
        reply = reply[3:-3].strip()
        reply = _strip_reply_prefix(reply)
        
    reply, facets_list = facets.enhance_tickers(reply)
    final_text = reply + sig
    
    if utils.count_graphemes(final_text) > config.MAX_COMMENT_CHARS:
        reply = utils.truncate_text(reply, config.MAX_COMMENT_CHARS, sig)
        if not reply or not isinstance(reply, str):
            return []
        reply = _strip_reply_prefix(reply)
        reply, facets_list = facets.enhance_tickers(reply)
        final_text = reply + sig

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
