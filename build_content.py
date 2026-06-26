import config
import utils
import generator
import logging
import random
import httpx
import asyncio
import io
import bsky
from PIL import Image
import urllib.parse

logger = logging.getLogger(__name__)

SIG_DIGEST = "\nQwen | Chainbase TOPS " + config.SIGNATURE_ICONS
SIG_TAVILY = "\nQwen | Tavily"
SIG_CHAINBASE = "\nQwen | Chainbase"
SIG_DEFAULT = "\nQwen"

def _get_signature(source: str, has_search: bool) -> str:
    if source == "tavily": return SIG_TAVILY
    if source == "chainbase": return SIG_CHAINBASE
    if has_search: return SIG_CHAINBASE
    return SIG_DEFAULT

def get_no_data_response(keyword: str) -> str:
    body = f'No data found for "{keyword}". Try rephrasing your query in a new comment or DYOR.'
    return f"{body}{SIG_DEFAULT}"

def _shorten_keyword(keyword: str, max_words: int = 3) -> str:
    words = keyword.split()
    if len(words) <= max_words: return keyword
    return ' '.join(words[:max_words])

async def _generate_digest_embed(client, trends: list, task_type: str, llm=None, refined_desc: str = "") -> dict | None:
    if not config.DIGEST_IMAGE_ENABLED: return None
    try:
        top_item = trends[0]
        keyword = top_item.get("keyword", "news")
        short_keyword = _shorten_keyword(keyword, 3)
        safe_keyword = short_keyword.replace("'", "").replace('"', '')[:50]
        visual_source = refined_desc if refined_desc else top_item.get("summary", "")
        safe_visual = visual_source.replace("'", "").replace('"', '')
        
        image_prompt = (
            f"A street art stencil mural in the style of Banksy on a weathered concrete wall. "
            f"The artwork depicts this scene: {safe_visual} "
            f"Monochrome stencil with selective color accents, satirical and thought-provoking composition. "
            f"The word '{safe_keyword}' appears as a small hand-painted tag in the corner. "
            f"If the topic mentions brands, cryptocurrencies, or projects, integrate their symbols as stenciled icons within the composition. "
            f"Drips, overspray, raw urban texture."
        )
        negative_prompt = (
            "blurry, low quality, watermark, signature, blank wall, only text, typography only, "
            "letters without illustration, random words, gibberish text, unrelated text, "
            "stray letters, nonsense words"
        )
        
        seed = random.randint(0, 2**31 - 1)
        image_bytes = await _call_image_gen(client, image_prompt, negative_prompt, seed)
        if not image_bytes: return None
        return await bsky.upload_digest_image(client, image_bytes, "image/png", alt=f"Digest: {keyword}")
    except Exception as e:
        logger.warning(f"[digest] Image pipeline failed: {e}")
        return None

async def _call_image_gen(client, prompt: str, negative: str, seed: int) -> bytes | None:
    models = ["flux", "turbo"]
    w, h = map(int, config.IMAGE_ASPECT_RATIO.split("x"))
    encoded = urllib.parse.quote(prompt, safe='')
    neg_encoded = urllib.parse.quote(negative, safe='')
    key_encoded = urllib.parse.quote(config.POLLINATIONS_API_KEY, safe='')
    
    for model in models:
        url = f"https://gen.pollinations.ai/image/{encoded}?width={w}&height={h}&seed={seed}&model={model}&enhance=true&nologo=true&negative_prompt={neg_encoded}&key={key_encoded}"
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                r = await client.get(url, timeout=120)
                if r.status_code == 200:
                    img = Image.open(io.BytesIO(r.content)).convert("RGB")
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG", optimize=True)
                    if buffer.tell() > 900 * 1024:
                        buffer = io.BytesIO()
                        img.save(buffer, format="JPEG", quality=85, optimize=True)
                    return buffer.getvalue()
                elif r.status_code in (402, 429):
                    if attempt < max_attempts - 1: await asyncio.sleep(30)
                    continue
                else:
                    if attempt < max_attempts - 1: await asyncio.sleep(10)
                    continue
            except Exception as e:
                if attempt < max_attempts - 1: await asyncio.sleep(10)
                continue
    return None

async def build_digest(llm, trends, task_type: str, client=None, max_total: int = config.MAX_COMMENT_CHARS) -> tuple[str, dict | None]:
    if not trends: return None, None
    sig = SIG_DIGEST
    emojis = config.TREND_EMOJIS
    stats_emoji = config.TREND_STATS_EMOJI
    sep = config.TREND_SCORE_SEPARATOR
    trophy = config.TREND_TROPHY
    refined_desc = ""
    
    if task_type == "digest_mini":
        lines = []
        for idx, item in enumerate(trends[:6]):
            kw = str(item.get("keyword", "?"))
            sc = item.get("score")
            st = str(item.get("rank_status", "same"))
            e = emojis.get(st.lower(), "")
            tr = f" {trophy}" if idx == 0 else ""
            lines.append(f"{e} {kw} {sep} {sc} {stats_emoji}{tr}")
            if len("\n".join(lines)) + len(sig) > max_total:
                lines.pop()
                break
        if not lines: return None, None
        body = "\n".join(lines)
    else:
        item = trends[0]
        kw = str(item.get("keyword", "?"))
        sc = item.get("score")
        st = str(item.get("rank_status", "same"))
        summary = str(item.get("summary", ""))
        e = emojis.get(st.lower(), "")
        tr = f" {trophy}"
        title = f"{(e + ' ') if e else ''}{kw} {sep} {sc} {stats_emoji}{tr}\n"
        fixed_len = len(title) + len(sig)
        max_desc = max_total - fixed_len
        if max_desc < 30: return None, None
        
        prompt_text = generator.load_prompt("digest_refine", keyword=kw, summary=summary, max_chars=min(max_desc, config.DIGEST_DESC_MAX_CHARS))
        prompt_text = str(prompt_text).strip()
        try:
            output = await asyncio.to_thread(llm, prompt_text, max_tokens=config.DIGEST_DESC_MAX_TOKENS, temperature=0.5)
            desc = output.get("choices", [{}])[0].get("text", "").strip()
            desc = utils.compress_numbers(desc)
        except Exception:
            desc = summary[:max_desc] if summary else "No summary available."
            
        desc_chars = utils.count_graphemes(desc)
        desc_limit = min(max_desc, config.DIGEST_DESC_MAX_CHARS)
        if desc_chars > desc_limit:
            desc = utils.truncate_text(desc, desc_limit, sig="")
            if utils.count_graphemes(desc) > desc_limit: return None, None
        refined_desc = desc
        body = title + desc
        
    final = body + sig
    if utils.count_graphemes(final) > max_total: return None, None
    
    embed = None
    if client and task_type == "digest_full":
        embed = await _generate_digest_embed(client, trends, task_type, llm=llm, refined_desc=refined_desc)
    return final, embed