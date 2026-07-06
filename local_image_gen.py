import os
import torch
from diffusers import FluxPipeline
from PIL import Image
import io
import logging
import config

logger = logging.getLogger(__name__)

_model = None
_model_path = os.path.join(os.path.dirname(__file__), "models", "flux1-schnell-Q4_K_S.gguf")

def _load_model():
    global _model
    if _model is not None:
        return _model

    if not os.path.exists(_model_path):
        logger.error(f"[local_image] GGUF not found: {_model_path}")
        return None

    logger.info(f"[local_image] Loading FLUX.1-schnell GGUF from {_model_path}...")
    try:
        token = os.environ.get("HF_API_TOKEN", "").strip()
        _model = FluxPipeline.from_single_file(
            _model_path,
            torch_dtype=torch.float32,
            token=token if token else None
        )
        _model.to("cpu")
        logger.info("[local_image] FLUX.1-schnell GGUF loaded successfully")
        return _model
    except Exception as e:
        logger.error(f"[local_image] Failed to load model: {e}")
        import traceback
        logger.error(f"[local_image] Traceback: {traceback.format_exc()[:800]}")
        return None

def generate_image(prompt: str, negative_prompt: str = "", width: int = 512, height: int = 512) -> bytes | None:
    try:
        pipe = _load_model()
        if pipe is None:
            logger.warning("[local_image] Model not loaded")
            return None

        steps = min(config.IMAGE_INFERENCE_STEPS, 20)
        guidance = 3.5

        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{prompt} Avoid: {negative_prompt}"

        logger.info(f"[local_image] Generating image ({steps} steps, guidance {guidance}): {full_prompt[:150]}...")
        
        image = pipe(
            prompt=full_prompt,
            num_inference_steps=steps,
            guidance_scale=guidance,
            width=width,
            height=height
        ).images[0]

        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        if buffer.tell() > 900 * 1024:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85, optimize=True)
            
        image_bytes = buffer.getvalue()
        logger.info(f"[local_image] Generated: {len(image_bytes)} bytes")
        return image_bytes
    except Exception as e:
        logger.warning(f"[local_image] Generation failed: {type(e).__name__}: {e}")
        import traceback
        logger.warning(f"[local_image] Traceback: {traceback.format_exc()[:500]}")
        return None
