import os
import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image
import io
import logging
import config

logger = logging.getLogger(__name__)

_model = None
_model_dir = os.path.join(os.path.dirname(__file__), "models", "animagine-xl")


def _load_model():
    global _model
    if _model is not None:
        return _model
    
    model_index = os.path.join(_model_dir, "model_index.json")
    if not os.path.exists(model_index):
        logger.error(f"[local_image] model_index.json not found: {model_index}")
        return None
    
    logger.info(f"[local_image] Loading Animagine XL from {_model_dir}...")
    
    try:
        _model = StableDiffusionXLPipeline.from_pretrained(
            _model_dir,
            torch_dtype=torch.float32,
            use_safetensors=True,
            local_files_only=True
        )
        _model.to("cpu")
        logger.info("[local_image] Animagine XL loaded successfully")
        return _model
    except Exception as e:
        logger.error(f"[local_image] Failed to load model: {e}")
        import traceback
        logger.error(f"[local_image] Traceback: {traceback.format_exc()[:800]}")
        return None


def generate_image(prompt: str, width: int = 512, height: int = 512) -> bytes | None:
    try:
        pipe = _load_model()
        if pipe is None:
            logger.warning("[local_image] Model not loaded")
            return None
        
        steps = config.IMAGE_INFERENCE_STEPS
        guidance = 7.0
        logger.info(f"[local_image] Generating image ({steps} steps, guidance {guidance}): {prompt[:100]}...")
        
        image = pipe(
            prompt=prompt,
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
