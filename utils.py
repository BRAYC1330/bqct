import re
import logging
import httpx
import config
import bsky
logger = logging.getLogger(__name__)

def clean_for_llm(text: str) -> str:
    if not text: return ""
    text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+', '', text)
    text = re.sub(r'(!t|!c)', '', text, flags=re.I)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[\*\_~`>|]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def count_graphemes(text: str) -> int:
    if not text: return 0
    return len(text.encode('utf-8').decode('utf-8', errors='ignore'))

def count_tokens(text: str, llm) -> int:
    if hasattr(llm, "tokenize"):
        return len(llm.tokenize(text.encode('utf-8')))
    return len(text) // 3

def truncate_text(text: str, max_len: int, sig: str = "") -> str:
    safe_len = max_len - len(sig)
    if len(text) <= safe_len:
        return text
    truncated = text[:safe_len]
    last_dot = truncated.rfind(".")
    return truncated[:last_dot+1].strip() if last_dot != -1 else truncated.rstrip()

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
        urls = re.findall(r'https?://\S+', raw_text)
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
