import os
import torch
from diffusers import FluxPipeline
from huggingface_hub import login
from PIL import Image
import io
import logging
import config

logger = logging.getLogger(__name__)

_model = None
_model_dir = os.path.join(os.path.dirname(__file__), "models", "flex1-alpha-8b")

def _load_model():
    global _model
    if _model is not None:
        return _model
    
    gguf_file = os.path.join(_model_dir, "Flex.1-alpha-Q4_K_M.gguf")
    if not os.path.exists(gguf_file):
        logger.error(f"[local_image] GGUF file not found: {gguf_file}")
        models_dir = os.path.join(os.path.dirname(__file__), "models")
        if os.path.exists(models_dir):
            logger.info(f"[local_image] Contents of models/: {os.listdir(models_dir)}")
        else:
            logger.error(f"[local_image] models/ directory not found")
        return None
    
    logger.info(f"[local_image] Loading Flex.1-alpha model from {gguf_file}...")
    
    try:
        hf_token = os.getenv("HF_API_TOKEN", "").strip() or None
        
        if hf_token:
            logger.info("[local_image] Logging in to HuggingFace Hub...")
            login(token=hf_token)
        else:
            logger.warning("[local_image] HF_API_TOKEN not found")
        
        _model = FluxPipeline.from_single_file(
            gguf_file,
            torch_dtype=torch.float32,
            token=hf_token
        )
        _model.to("cpu")
        logger.info("[local_image] Flex.1-alpha model loaded successfully")
        return _model
    except Exception as e:
        logger.error(f"[local_image] Failed to load model: {e}")
        import traceback
        logger.error(f"[local_image] Traceback: {traceback.format_exc()[:800]}")
        return None

def generate_image(prompt: str, negative_prompt: str = "", width: int = 1024, height: int = 1024) -> bytes | None:
    try:
        pipe = _load_model()
        if pipe is None:
            logger.warning("[local_image] Model not loaded")
            return None
        
        steps = config.IMAGE_INFERENCE_STEPS
        guidance = 3.5
        logger.info(f"[local_image] Generating image ({steps} steps, guidance {guidance}): {prompt[:100]}...")
        
        enhanced_negative = config.IMAGE_NEGATIVE_PROMPT if hasattr(config, 'IMAGE_NEGATIVE_PROMPT') else (
            "blurry, low quality, watermark, signature, distorted, deformed, "
            "bad anatomy, wrong proportions, extra limbs, mutated hands, "
            "poorly drawn face, mutation, ugly, duplicate, morbid, "
            "out of frame, cropped, dark, low contrast, sepia, brown tint, washed out, "
            "photorealistic, 3D render, digital art, cartoon, anime, illustration, "
            "smooth gradients, airbrushed, clean lines, professional photography, "
            "colorful, bright colors, multiple colors, rainbow, pastel"
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
