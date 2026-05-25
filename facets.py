import re
import logging
import config
from typing import List, Tuple

logger = logging.getLogger(__name__)

def _utf16_len(text: str) -> int:
    return len(text.encode('utf-16-le')) // 2

def validate_facets(text: str, facets: List[dict]) -> List[dict]:
    if not facets: return []
    text_len = _utf16_len(text)
    return [f for f in facets if 0 <= f["index"]["byteStart"] < f["index"]["byteEnd"] <= text_len]

def enhance_tickers(text: str) -> Tuple[str, List[dict]]:
    if not text: return "", []
    pattern = re.compile(r'\$(?![0-9])([A-Za-z]{1,10})(?![A-Za-z0-9])')
    hashtag_pattern = re.compile(r'#([a-zA-Z0-9_]+)')
    seen, ticker_positions, parts = set(), [], []
    last_idx = 0

    for m in pattern.finditer(text):
        ticker = m.group(1).upper()
        if ticker not in seen:
            seen.add(ticker)
            parts.append(text[last_idx:m.start()])
            bs = _utf16_len("".join(parts))
            ticker_full = m.group(0)
            parts.extend([ticker_full, f" {config.TICKER_LINK_EMOJI} ", ticker_full])
            be = bs + _utf16_len(ticker_full)
            ticker_positions.append((ticker, bs, be))
            last_idx = m.end()

    parts.append(text[last_idx:])
    new_text = "".join(parts)
    facets = [{"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": "app.bsky.richtext.facet#link", "uri": f"https://dexscreener.com/search?q={t}"}]} for t, bs, be in ticker_positions]

    for m in hashtag_pattern.finditer(new_text):
        bs, be = _utf16_len(new_text[:m.start()]), _utf16_len(new_text[:m.end()])
        facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}]})

    return new_text, validate_facets(new_text, facets)

def generate_digest_facets(text: str) -> List[dict]:
    if not text: return []
    pattern = re.compile(r'\$(?![0-9])([A-Za-z]{1,10})(?![A-Za-z0-9])')
    hashtag_pattern = re.compile(r'#([a-zA-Z0-9_]+)')
    facets = []

    for m in pattern.finditer(text):
        bs, be = _utf16_len(text[:m.start()]), _utf16_len(text[:m.end()])
        facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": "app.bsky.richtext.facet#link", "uri": f"https://dexscreener.com/search?q={m.group(1).upper()}"}]})

    for m in hashtag_pattern.finditer(text):
        bs, be = _utf16_len(text[:m.start()]), _utf16_len(text[:m.end()])
        facets.append({"index": {"byteStart": bs, "byteEnd": be}, "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}]})

    return validate_facets(text, facets)
