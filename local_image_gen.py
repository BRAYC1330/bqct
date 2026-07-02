import os
import torch
from diffusers import AutoPipelineForText2Image
from huggingface_hub import login
from PIL import Image
import io
import logging
import config

logger = logging.getLogger(__name__)

_model = None
_model_dir = os.path.join(os.path.dirname(__file__), "models", "sdxl-turbo")

def _load_model():
    global _model
    if _model is not None:
        return _model
    
    gguf_file = os.path.join(_model_dir, "sdxl-turbo-q4_0.gguf")
    if not os.path.exists(gguf_file):
        logger.error(f"[local_image] GGUF file not found: {gguf_file}")
        models_dir = os.path.join(os.path.dirname(__file__), "models")
        if os.path.exists(models_dir):
            logger.info(f"[local_image] Contents of models/: {os.listdir(models_dir)}")
        else:
            logger.error(f"[local_image] models/ directory not found")
        return None
    
    logger.info(f"[local_image] Loading SDXL-Turbo model from {gguf_file}...")
    
    try:
        hf_token = os.getenv("HF_API_TOKEN", "").strip() or None
        
        if hf_token:
            logger.info("[local_image] Logging in to HuggingFace Hub...")
            login(token=hf_token)
        else:
            logger.warning("[local_image] HF_API_TOKEN not found")
        
        _model = AutoPipelineForText2Image.from_single_file(
            gguf_file,
            torch_dtype=torch.float32,
            token=hf_token
        )
        _model.to("cpu")
        logger.info("[local_image] SDXL-Turbo model loaded successfully")
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
        
        logger.info(f"[local_image] Generating image (1 step, guidance 0.0): {prompt[:100]}...")
        
        image = pipe(
            prompt=prompt,
            num_inference_steps=1,
            guidance_scale=0.0,
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
