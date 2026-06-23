import re
import logging
import config
from typing import List, Tuple

logger = logging.getLogger(__name__)

def _parse_facets(text: str) -> List[dict]:
    if not text: return []
    facets = []
    pattern = re.compile(r'\$(?![0-9])([A-Za-z]{1,10})(?![A-Za-z0-9])')
    hashtag_pattern = re.compile(r'#([a-zA-Z0-9_]+)')
    
    for m in pattern.finditer(text):
        ticker = m.group(1).upper()
        bs = len(text[:m.start()].encode('utf-8'))
        be = len(text[:m.end()].encode('utf-8'))
        facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": "app.bsky.richtext.facet#link", "uri": f"https://dexscreener.com/search?q={ticker}"}]})
        
    for m in hashtag_pattern.finditer(text):
        bs = len(text[:m.start()].encode('utf-8'))
        be = len(text[:m.end()].encode('utf-8'))
        facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}]})
        
    return facets

def validate_facets(text: str, facets: List[dict]) -> List[dict]:
    if not facets: return []
    text_bytes = text.encode('utf-8')
    text_len = len(text_bytes)
    return [f for f in facets if 0 <= f["index"]["byteStart"] < f["index"]["byteEnd"] <= text_len]

def enhance_tickers(text: str) -> Tuple[str, List[dict]]:
    if not text: return "", []
    pattern = re.compile(r'\$(?![0-9])([A-Za-z]{1,10})(?![A-Za-z0-9])')
    seen = set()
    parts = []
    last_idx = 0
    for m in pattern.finditer(text):
        ticker = m.group(1).upper()
        if ticker not in seen:
            seen.add(ticker)
            parts.append(text[last_idx:m.start()])
            parts.append(m.group(0))
            parts.append(f" {config.TICKER_LINK_EMOJI} ")
            parts.append(m.group(0))
            last_idx = m.end()
    parts.append(text[last_idx:])
    new_text = "".join(parts)
    return new_text, validate_facets(new_text, _parse_facets(new_text))

def generate_digest_facets(text: str) -> List[dict]:
    if not text: return []
    return validate_facets(text, _parse_facets(text))
