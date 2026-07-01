import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image
import io
import logging
import config

logger = logging.getLogger(__name__)

_model = None
_model_path = "models/sdxl-turbo"

def _load_model():
    global _model
    if _model is not None:
        return _model
    
    logger.info(f"[local_image] Loading model from {_model_path}...")
    
    try:
        _model = StableDiffusionXLPipeline.from_pretrained(
            _model_path,
            torch_dtype=torch.float32,
            use_safetensors=True,
            local_files_only=True
        )
        _model.to("cpu")
        logger.info("[local_image] Model loaded successfully")
        return _model
    except Exception as e:
        logger.error(f"[local_image] Failed to load model: {e}")
        return None

def generate_image(prompt: str, negative_prompt: str = "", width: int = 1024, height: int = 1024) -> bytes | None:
    try:
        pipe = _load_model()
        if pipe is None:
            logger.warning("[local_image] Model not loaded")
            return None
        
        steps = config.IMAGE_INFERENCE_STEPS
        guidance = 0.0 if steps == 1 else 1.0
        logger.info(f"[local_image] Generating image ({steps} steps): {prompt[:100]}...")
        
        enhanced_negative = config.IMAGE_NEGATIVE_PROMPT if hasattr(config, 'IMAGE_NEGATIVE_PROMPT') else (
            "blurry, low quality, watermark, signature, distorted, deformed, "
            "bad anatomy, wrong proportions, extra limbs, mutated hands, "
            "poorly drawn face, mutation, ugly, duplicate, morbid, "
            "out of frame, cropped, dark, low contrast"
        )
        if negative_prompt:
            enhanced_negative = f"{negative_prompt}, {enhanced_negative}"
        
        image = pipe(
            prompt=prompt,
            negative_prompt=enhanced_negative,
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
