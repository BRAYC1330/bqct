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
    return utils.truncate_text(reply, max_body).strip() + sig
async def _generate_digest_embed(client, trends: list, task_type: str) -> dict | None:
    if not config.DIGEST_IMAGE_ENABLED: return None
    try:
        top_item = trends[0]
        keyword = top_item.get("keyword", "crypto market")
        prompt, negative = prompt_engine.build_image_prompt(keyword)
        seed = random.randint(0, 2**31 - 1)
        image_bytes = await _call_image_gen(prompt, negative, seed)
        if not image_bytes: return None
        return await bsky.upload_digest_image(client, image_bytes, "image/png", alt=f"Scene: {keyword}")
    except Exception as e:
        logger.warning(f"[digest] Image pipeline failed: {e}")
        return None
async def _call_image_gen(prompt: str, negative: str, seed: int) -> bytes | None:
    try:
        if not config.HF_API_TOKEN: return None
        
        # Прямой вызов бесплатного инференс-эндпоинта (минуя провайдеров)
        url = f"https://api-inference.huggingface.co/models/{config.HF_IMAGE_MODEL}"
        headers = {
            "Authorization": f"Bearer {config.HF_API_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": prompt,
            "parameters": {
                "negative_prompt": negative,
                "guidance_scale": 7.5,
                "num_inference_steps": 30,
                "seed": seed
            }
        }
        
        async with httpx.AsyncClient() as http:
            r = await http.post(url, headers=headers, json=payload, timeout=90)
            
            if r.status_code == 503:
                logger.info("[image_gen] Model loading, waiting 20s...")
                await asyncio.sleep(20)
                r = await http.post(url, headers=headers, json=payload, timeout=90)
            
            if r.status_code != 200:
                logger.warning(f"[image_gen] API error {r.status_code}: {r.text[:200]}")
                return None
            
            # Конвертируем в правильный размер для Bluesky
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            w, h = map(int, config.IMAGE_ASPECT_RATIO.split("x"))
            img.thumbnail((w, h), Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()
        
    except Exception as e:
        logger.warning(f"[image_gen] HF call failed: {e}")
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
