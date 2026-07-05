import os
import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image, ImageEnhance
import io
import logging
import config

logger = logging.getLogger(__name__)

_model = None
_model_dir = os.path.join(os.path.dirname(__file__), "models", "sdxl-turbo")
_lora_dir = os.path.join(os.path.dirname(__file__), "models", "banksy-lora")


def remove_yellow_tint(image):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.2)
    image = image.convert('L')
    image = image.convert('RGB')
    return image


def _load_model():
    global _model
    if _model is not None:
        return _model
    
    model_index = os.path.join(_model_dir, "model_index.json")
    if not os.path.exists(model_index):
        logger.error(f"[local_image] model_index.json not found: {model_index}")
        return None
    
    logger.info(f"[local_image] Loading SDXL-Turbo from {_model_dir}...")
    
    try:
        _model = StableDiffusionXLPipeline.from_pretrained(
            _model_dir,
            torch_dtype=torch.float32,
            use_safetensors=True,
            local_files_only=True
        )
        _model.to("cpu")
        
        # ИСПРАВЛЕНО: banksy-lora (без k) и Banksy Style (без k)
        lora_file = os.path.join(_lora_dir, "Banksy Style.safetensors")
        if os.path.exists(lora_file):
            logger.info(f"[local_image] Loading Banksy LoRA from {lora_file}...")
            try:
                _model.load_lora_weights(lora_file)
                logger.info("[local_image] Banksy LoRA loaded successfully")
            except Exception as lora_err:
                logger.warning(f"[local_image] LoRA load failed, using base model: {lora_err}")
        else:
            logger.warning(f"[local_image] LoRA not found at {lora_file}, using base model")
        
        logger.info("[local_image] Model loaded successfully")
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
        
        steps = config.IMAGE_INFERENCE_STEPS
        guidance = 1.0
        logger.info(f"[local_image] Generating image ({steps} steps, guidance {guidance}): {prompt[:100]}...")
        
        enhanced_negative = config.IMAGE_NEGATIVE_PROMPT if hasattr(config, 'IMAGE_NEGATIVE_PROMPT') else (
            "blurry, low quality, watermark, signature, distorted, deformed, "
            "bad anatomy, wrong proportions, extra limbs, mutated hands, "
            "poorly drawn face, mutation, ugly, duplicate, morbid, "
            "out of frame, cropped, dark, low contrast, "
            "hands, fingers, extra fingers, missing fingers, text, words, letters, "
            "crowd, many people, messy, cluttered, complex background"
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
        
        image = remove_yellow_tint(image)
        
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
