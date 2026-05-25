import config
import utils
import generator
import logging
import random
import httpx
import asyncio
import io
import bsky
import prompt_engine
from PIL import Image
import urllib.parse
logger = logging.getLogger(__name__)
SIG_DIGEST = "\n\nQwen | Chainbase crypto TOPS " + config.SIGNATURE_ICONS
SIG_TAVILY = "\n\nQwen | Tavily"
SIG_CHAINBASE = "\n\nQwen | Chainbase"
SIG_DEFAULT = "\n\nQwen"
def _get_signature(source: str, has_search: bool) -> str:
    if source == "tavily": return SIG_TAVILY
    if source == "chainbase": return SIG_CHAINBASE
    if has_search: return SIG_CHAINBASE
    return SIG_DEFAULT
def get_no_data_response(keyword: str) -> str:
    body = f'No data found for "{keyword}". Try rephrasing your query in a new comment or DYOR.'
    return f"{body}{SIG_DEFAULT}"
async def build_reply(llm, thread_ctx: str, query: str, search_data: str = "", source: str = "", max_total: int = config.MAX_COMMENT_CHARS) -> str:
    sig = _get_signature(source, bool(search_data))
    max_body = max_total - len(sig)
    if search_data:
        ctx = f"{search_data}\n{thread_ctx}"
    else:
        ctx = thread_ctx
    reply = generator.get_answer(llm, ctx, query, max_chars=max_body, temperature=0.5)
    reply = utils.compress_numbers(reply)
    return utils.truncate_text(reply, max_body).strip() + sig
async def _generate_digest_embed(client, trends: list, task_type: str) -> dict | None:
    if not config.DIGEST_IMAGE_ENABLED: return None
    try:
        top_item = trends[0]
        keyword = top_item.get("keyword", "crypto market")
        prompt, negative = prompt_engine.build_image_prompt(keyword)
        seed = random.randint(0, 2**31 - 1)
        image_bytes = await _call_image_gen(prompt, seed)
        if not image_bytes: return None
        return await bsky.upload_digest_image(client, image_bytes, "image/png", alt=f"Scene: {keyword}")
    except Exception as e:
        logger.warning(f"[digest] Image pipeline failed: {e}")
        return None
async def _call_image_gen(prompt: str, seed: int) -> bytes | None:
    try:
        w, h = map(int, config.IMAGE_ASPECT_RATIO.split("x"))
        encoded = urllib.parse.quote(prompt, safe='')
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&seed={seed}&model=flux&nologo=true"
        
        for attempt in range(2):
            async with httpx.AsyncClient() as http:
                r = await http.get(url, timeout=90)
                if r.status_code == 200:
                    img = Image.open(io.BytesIO(r.content)).convert("RGB")
                    logger.info(f"[image_gen] Native size: {img.size}")
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG", optimize=True)
                    if buffer.tell() > 900 * 1024:
                        buffer = io.BytesIO()
                        img.save(buffer, format="JPEG", quality=85, optimize=True)
                    return buffer.getvalue()
                elif r.status_code == 500 and attempt == 0:
                    logger.warning("[image_gen] Pollinations 500, retrying with default model...")
                    url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&seed={seed}&nologo=true"
                    continue
                else:
                    logger.warning(f"[image_gen] Pollinations error: {r.status_code}")
                    return None
    except Exception as e:
        logger.warning(f"[image_gen] Pollinations call failed: {type(e).__name__}: {e}")
        return None
async def build_digest(llm, trends, task_type: str, client=None, max_total: int = config.MAX_COMMENT_CHARS) -> tuple[str, dict | None]:
    if not trends: return None, None
    sig = SIG_DIGEST
    emojis = config.TREND_EMOJIS
    stats_emoji = config.TREND_STATS_EMOJI
    sep = config.TREND_SCORE_SEPARATOR
    trophy = config.TREND_TROPHY
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
        title = f"{(e + ' ') if e else ''}{kw} {sep} {sc} {stats_emoji}{tr}\n\n"
        fixed_len = len(title) + len(sig)
        max_desc = max_total - fixed_len
        if max_desc < 30:
            logger.warning(f"[digest] max_desc too small: {max_desc} < 30")
            return None, None
        prompt_text = generator.load_prompt("digest_refine", keyword=kw, summary=summary, max_chars=min(max_desc, config.DIGEST_DESC_MAX_CHARS))
        prompt_text = str(prompt_text).strip()
        if config.RAW_DEBUG:
            logger.info("=== [DIGEST PROMPT] ===")
            logger.info(prompt_text)
            logger.info("=== [DIGEST PROMPT] END ===")
        try:
            output = llm(prompt_text, max_tokens=config.DIGEST_DESC_MAX_TOKENS, temperature=0.5)
            desc = output.get("choices", [{}])[0].get("text", "").strip()
            desc = utils.compress_numbers(desc)
            if config.RAW_DEBUG:
                logger.info("=== [DIGEST RAW OUTPUT] ===")
                logger.info(desc)
                logger.info("=== [END DIGEST OUTPUT] ===")
        except TypeError as e:
            logger.error(f"[digest] LLM TypeError: {e} | prompt_type={type(prompt_text)} | len={len(prompt_text)}")
            desc = summary[:max_desc] if summary else "No summary available."
        except Exception as e:
            logger.error(f"[digest] LLM failed")
            desc = summary[:max_desc] if summary else "No summary available."
        desc_chars = utils.count_graphemes(desc)
        desc_limit = min(max_desc, config.DIGEST_DESC_MAX_CHARS)
        if desc_chars > desc_limit:
            logger.warning(f"[digest] Model output too long ({desc_chars} > {desc_limit}), truncating smartly")
            desc = utils.truncate_text(desc, desc_limit, sig="")
            desc_chars = utils.count_graphemes(desc)
            logger.info(f"[digest] Truncated to {desc_chars} chars")
        if desc_chars > desc_limit:
            logger.warning(f"[digest] Still too long after truncation, returning None")
            return None, None
        body = title + desc
    final = body + sig
    final_len = utils.count_graphemes(final)
    if final_len > max_total:
        logger.warning(f"[digest] Final post too long: {final_len} > {max_total} | type={task_type}")
        return None, None
    if config.RAW_DEBUG:
        logger.info("=== [FINAL DIGEST POST] ===")
        logger.info(final)
        logger.info("=== [END FINAL POST] ===")
    embed = None
    if client and task_type == "digest_full":
        embed = await _generate_digest_embed(client, trends, task_type)
    return final, embed
