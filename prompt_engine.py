import logging
logger = logging.getLogger(__name__)
def build_image_prompt(keyword: str, summary: str = "") -> tuple[str, str]:
    prompt = f"graffiti style. {keyword}. {summary}"
    negative = "text, watermark, signature, blurry, low quality, extra limbs, deformed"
    logger.info(f"[prompt_engine] Graffiti prompt for: {keyword}")
    return prompt, negative
