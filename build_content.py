import re
import config
import utils
import generator
import logging
import bsky

logger = logging.getLogger(__name__)

SIG_DIGEST = "\n\nQwen | Chainbase TOPS " + config.SIGNATURE_ICONS
SIG_TAVILY = "\n\nQwen | Tavily"
SIG_CHAINBASE = "\n\nQwen | Chainbase"
SIG_DEFAULT = "\n\nQwen"

def _get_llm_text(response) -> str:
    if isinstance(response, str): return response.strip()
    if not isinstance(response, dict): return ""
    return response.get("choices", [{}])[0].get("text", "").strip()

def _get_signature(source: str, has_search: bool) -> str:
    if source == "tavily":
        return SIG_TAVILY
    if source == "chainbase":
        return SIG_CHAINBASE
    if has_search:
        return SIG_CHAINBASE
    return SIG_DEFAULT

def get_no_data_response(keyword: str) -> str:
    body = f'No data found for "{keyword}". Try rephrasing your query in a new comment or DYOR.'
    return f"{body}{SIG_DEFAULT}"

def _shorten_keyword(keyword: str, max_words: int = 3) -> str:
    words = keyword.split()
    if len(words) <= max_words:
        return keyword
    return ' '.join(words[:max_words])

def _generate_chart_candles(llm, context: str) -> str:
    if not llm:
        return ""
    try:
        prompt_text = generator.load_prompt("chart_scene", context=context[:1500])
        prompt_text = str(prompt_text).strip()
        
        if config.RAW_DEBUG:
            logger.info("=== [CHART SCENE PROMPT] ===")
            logger.info(prompt_text)
            logger.info("=== [END CHART SCENE PROMPT] ===")
            
        output = llm(prompt_text, max_tokens=500, temperature=0.3)
        raw = _get_llm_text(output)
        return raw
    except Exception as e:
        logger.warning(f"[digest] Chart candles generation failed: {e}")
        return ""

def _log_candles(candles_json: str) -> None:
    try:
        import chart_renderer
        candles = chart_renderer.parse_candles_json(candles_json)
        if not candles:
            logger.info("[digest] Candles parse failed, no coordinates to log")
            return
        candles = chart_renderer.validate_and_fix_candles(candles)
        logger.info(f"[digest] === CHART COORDINATES ({len(candles)} candles) ===")
        for i, c in enumerate(candles):
            direction = "UP" if c['c'] >= c['o'] else "DOWN"
            logger.info(f"[digest] Candle {i+1:2d}: O={c['o']:.1f} H={c['h']:.1f} L={c['l']:.1f} C={c['c']:.1f} | {direction}")
        peak = max(c['h'] for c in candles)
        drop = min(c['l'] for c in candles)
        start = candles[0]['o']
        now = candles[-1]['c']
        logger.info(f"[digest] Stats: START={start:.1f} PEAK={peak:.1f} DROP={drop:.1f} NOW={now:.1f}")
        logger.info("[digest] === END COORDINATES ===")
    except Exception as e:
        logger.warning(f"[digest] Candle logging failed: {e}")

async def _generate_digest_embed(client, trends, task_type, llm=None, summary: str = "") -> dict | None:
    if not config.DIGEST_IMAGE_ENABLED:
        return None
    try:
        import chart_renderer
        top_item = trends[0]
        keyword = top_item.get("keyword", "news")
        short_keyword = _shorten_keyword(keyword, 3)
        safe_subtitle = short_keyword.replace("'", "").replace('"', '').upper()[:50]
        
        candles_json = _generate_chart_candles(llm, summary)
        if not candles_json:
            logger.error("[digest] Chart candles generation returned empty, failing digest")
            return None
        logger.info(f"[digest] Raw Qwen output: {candles_json[:500]}")
        _log_candles(candles_json)
        image_bytes = chart_renderer.generate_chart_image(
            candles_json,
            title="AI SENTIMENT INDEX",
            subtitle=safe_subtitle
        )
        if not image_bytes:
            logger.error("[digest] Chart render failed, failing digest")
            return None
        logger.info(f"[digest] Chart rendered: {len(image_bytes)} bytes")
        return await bsky.upload_digest_image(client, image_bytes, "image/png", alt=f"Digest: {keyword}")
    except Exception as e:
        logger.warning(f"[digest] Image pipeline failed: {e}")
        import traceback
        logger.warning(f"[digest] Traceback: {traceback.format_exc()[:500]}")
        return None

async def build_digest(llm, trends, task_type: str, client=None, max_total: int = config.MAX_COMMENT_CHARS) -> tuple[str, dict | None]:
    if not trends:
        return None, None
    sig = SIG_DIGEST
    emojis = config.TREND_EMOJIS
    stats_emoji = config.TREND_STATS_EMOJI
    sep = config.TREND_SCORE_SEPARATOR
    trophy = config.TREND_TROPHY
    refined_desc = ""
    summary = ""
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
        if not lines:
            return None, None
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
            logger.info("=== [DIGEST PROMPT END ===")
        try:
            output = llm(prompt_text, max_tokens=config.DIGEST_DESC_MAX_TOKENS, temperature=0.5)
            desc = _get_llm_text(output)
            desc = utils.compress_numbers(desc)
            if config.RAW_DEBUG:
                logger.info("=== [DIGEST RAW OUTPUT] ===")
                logger.info(desc)
                logger.info("=== [END DIGEST OUTPUT] ===")
        except TypeError as e:
            logger.error(f"[digest] LLM TypeError: {repr(e)} | prompt_type={type(prompt_text)} | len={len(prompt_text)}")
            desc = summary[:max_desc] if summary else "No summary available."
        except Exception as e:
            logger.error(f"[digest] LLM failed: {repr(e)}")
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
        refined_desc = desc
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
        embed = await _generate_digest_embed(client, trends, task_type, llm=llm, summary=summary)
        if embed is None:
            logger.error("[digest] Image generation failed for digest_full, failing entire digest")
            return None, None
    return final, embed
