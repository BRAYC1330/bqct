import re
import logging
import config
from typing import List, Tuple

logger = logging.getLogger(__name__)

def validate_facets(text: str, facets: List[dict]) -> List[dict]:
    if not facets: return []
    text_bytes = text.encode('utf-8')
    text_len = len(text_bytes)
    return [f for f in facets if 0 <= f["index"]["byteStart"] < f["index"]["byteEnd"] <= text_len]

def enhance_tickers(text: str) -> Tuple[str, List[dict]]:
    if not text: return "", []
    pattern = re.compile(r'\$([A-Za-z][A-Za-z0-9]{1,9})\b')
    hashtag_pattern = re.compile(r'#([a-zA-Z0-9_]+)')
    seen = set()
    parts = []
    last_idx = 0
    for m in pattern.finditer(text):
        ticker = m.group(1).upper()
        if ticker not in seen:
            seen.add(ticker)
            parts.append(text[last_idx:m.start()])
            parts.append(f"{m.group(0)} {config.TICKER_LINK_EMOJI}")
            last_idx = m.end()
    parts.append(text[last_idx:])
    new_text = "".join(parts)
    facets = []
    for m in pattern.finditer(new_text):
        ticker = m.group(1).upper()
        byte_start = len(new_text[:m.start()].encode('utf-8'))
        byte_end = len(new_text[:m.end()].encode('utf-8'))
        facets.append({"index": {"byteStart": byte_start, "byteEnd": byte_end}, "features": [{"$type": "app.bsky.richtext.facet#link", "uri": f"https://dexscreener.com/search?q={ticker}"}]})
    for m in hashtag_pattern.finditer(new_text):
        bs = len(new_text[:m.start()].encode('utf-8'))
        be = len(new_text[:m.end()].encode('utf-8'))
        facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}]})
    return new_text, validate_facets(new_text, facets)

def generate_digest_facets(text: str) -> List[dict]:
    if not text: return []
    pattern = re.compile(r'\$([A-Za-z][A-Za-z0-9]{1,9})\b')
    hashtag_pattern = re.compile(r'#([a-zA-Z0-9_]+)')
    facets = []
    for m in pattern.finditer(text):
        ticker = m.group(1).upper()
        bs = len(text[:m.start()].encode('utf-8'))
        be = len(text[:m.end()].encode('utf-8'))
        facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": "app.bsky.richtext.facet#link", "uri": f"https://dexscreener.com/search?q={ticker}"}]})
    for m in hashtag_pattern.finditer(text):
        bs = len(text[:m.start()].encode('utf-8'))
        be = len(text[:m.end()].encode('utf-8'))
        facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}]})
    return validate_facets(text, facets)