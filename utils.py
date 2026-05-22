import regex
import logging
import httpx
import config
import bsky
logger = logging.getLogger(__name__)
def clean_for_llm(text: str) -> str:
    if not text: return ""
    text = regex.sub(r'[\p{Emoji}\p{Extended_Pictographic}]+', '', text)
    text = regex.sub(r'(!t|!c)', '', text, flags=regex.I)
    text = regex.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = regex.sub(r'https?://\S+', '', text)
    text = regex.sub(r'[\*\_#~`>|]', '', text)
    text = regex.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    return regex.sub(r'\s+', ' ', text).strip()
def count_graphemes(text: str) -> int:
    return len(regex.findall(r'\X', text))
def count_tokens(text: str, llm) -> int:
    if hasattr(llm, "tokenize"):
        return len(llm.tokenize(text.encode('utf-8')))
    return len(text) // 3
def truncate_text(text: str, max_len: int, sig: str = "") -> str:
    safe_len = max_len - len(sig)
    truncated = text[:safe_len]
    last_dot = truncated.rfind(".")
    return truncated[:last_dot+1] if last_dot != -1 else truncated.rstrip()
def is_english(text: str) -> bool:
    if not text: return False
    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars: return True
    return (sum(1 for c in alpha_chars if c.isascii()) / len(alpha_chars)) >= 0.7
async def _format_thread_for_llm(chain: dict, owner_did: str, bot_did: str, client: httpx.AsyncClient, max_recent: int = 5) -> str:
    if not chain: return ""
    root = clean_for_llm(chain.get("root_text", ""))
    posts = chain.get("chain", [])
    recent_posts = posts[-max_recent:] if len(posts) > max_recent else posts
    dialogue = []
    seen_hashes = set()
    seen_hashes.add(hash(root))
    for post in recent_posts:
        rec = post.get("record", {})
        author = post.get("author", {})
        did = author.get("did", "")
        raw_text = rec.get("text", "")
        text = clean_for_llm(raw_text)
        if not text or hash(text) in seen_hashes: continue
        seen_hashes.add(hash(text))
        embed = rec.get("embed")
        embed_txt = bsky._extract_embed_text(embed)
        if embed_txt: text += f" [EMBED: {embed_txt}]"
        urls = regex.findall(r'https?://\S+', raw_text)
        for u in urls:
            content = await bsky._fetch_url_content(client, u)
            if content: text += f" [LINK: {content[:config.MAX_LINK_CONTENT_SIZE]}]"
        if did == owner_did: prefix = "OWNER:"
        elif did == bot_did: prefix = "BOT:"
        else: prefix = "USER:"
        dialogue.append(f"{prefix} {text}")
    parts = [f"[ROOT]\n{root}"]
    if dialogue: parts.append(f"[RECENT]\n" + "\n".join(dialogue))
    return "\n".join(parts)