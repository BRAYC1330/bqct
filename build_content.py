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


def _generate_banksy_scene(llm, context: str) -> str:
    if not llm:
        return ""
    try:
        prompt_text = generator.load_prompt("banksy_scene", context=context[:800])
        prompt_text = str(prompt_text).strip()
        output = llm(prompt_text, max_tokens=25, temperature=0.6)
        scene = _get_llm_text(output)
        scene = scene.strip('"').strip("'").strip()
        scene = re.sub(r'^(visual\s*(?:scene|description)?:?\s*|scene:?\s*|mural:?\s*|subject\s*description:?\s*)', '', scene, flags=re.I).strip()
        if scene.startswith("```") and scene.endswith("```"):
            scene = scene[3:-3].strip()
        scene = scene.strip('`"\'').strip()
        if len(scene) > 120:
            scene = scene[:120].rsplit(' ', 1)[0]
        logger.info(f"[digest] Banksky subject: {scene[:80]}")
        return scene
    except Exception as e:
        logger.warning(f"[digest] Banksky scene generation failed: {e}")
        return ""


async def _generate_digest_embed(client, trends, task_type, llm=None, visual_scene: str = "", full_context: str = "") -> dict | None:
    if not config.DIGEST_IMAGE_ENABLED:
        return None
    try:
        import local_image_gen
        
        top_item = trends[0]
        keyword = top_item.get("keyword", "news")

        short_keyword = _shorten_keyword(keyword, 3)
        safe_keyword = short_keyword.replace("'", "").replace('"', '').replace('-', ' ')[:50]

        safe_visual = visual_scene.replace("'", "").replace('"', '')

        # ФОРМАТ ИЗ РАБОЧИХ ПРИМЕРОВ:
        # Banksky Style page в конце (как в примерах 2 и 3)
        # + художественные термины (stencil print, sprayed poster)
        # + другие художники для стиля (Bernard Buffet, Aleksi Briclot)
        # + "on concrete wall" чтобы был на стене
        image_prompt = (
            f"banksky stencil print of {safe_visual}, "
            f"satirical political cartoon, influenced by Bernard Buffet, "
            f"high contrast black and white with selective red accents, "
            f"minimal shading, FLAT COLORS, on concrete wall, Banksky Style page"
        )

        # УСИЛЕННЫЙ NEGATIVE PROMPT: запрет рук + артефакты
        negative_prompt = (
            "worst quality, low quality, blurry, deformed, disfigured, "
            "extra limbs, extra fingers, bad anatomy, bad hands, hands, fingers, "
            "missing fingers, mutated hands, ugly hands, deformed hands, "
            "cropped, watermark, text, signature, jpeg artifacts, "
            "ugly face, asymmetric eyes, extra arms, extra legs, merged limbs, "
            "crowd, many people, messy, cluttered, colorful, photorealistic, "
            "3D render, digital art, smooth gradients"
        )

        logger.info(f"[digest] Subject: {safe_visual[:80]}")
        logger.info(f"[digest] Short keyword: {safe_keyword}")
        logger.info(f"[digest] Image prompt ({len(image_prompt.split())} words): {image_prompt}")

        w, h = 512, 512
        image_bytes = local_image_gen.generate_image(image_prompt, negative_prompt, w, h)
        
        if not image_bytes:
            logger.warning("[digest] Image generation failed, posting text-only")
            return None
        return await bsky.upload_digest_image(client, image_bytes, "image/png", alt=f"Digest: {keyword}")
    except Exception as e:
        logger.warning(f"[digest] Image pipeline failed: {e}")
        return None


async def build_digest(llm, trends, task_type: str, client=None, max_total: int = config.MAX_COMMENT_CHARS) -> tuple[str, dict | None]:
    if not trends:
        return None, None
    sig = SIG_DIGEST
    emojis = config.TREND_EMOJIS
    stats_emoji = config.TREND_STATS_EMOJI
    sep = config.TREND_SCORE_SEPARATOR
    trophy = config.TREND_TROPHY
    visual_scene = ""
    full_context = ""
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
        full_context = f"{kw}\n\n{summary}"
        visual_scene = _generate_banksy_scene(llm, full_context)
        if not visual_scene:
            visual_scene = desc[:200]
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
        embed = await _generate_digest_embed(client, trends, task_type, llm=llm, visual_scene=visual_scene, full_context=full_context)
        if embed is None:
            logger.warning("[digest] Image generation failed for digest_full, skipping entire digest")
            return None, None
    return final, embed
