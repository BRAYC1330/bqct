import os
import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image
import io
import logging
import config

logger = logging.getLogger(__name__)

_model = None
_model_dir = os.path.join(os.path.dirname(__file__), "models", "sdxl-base")
_lora_path = os.path.join(os.path.dirname(__file__), "models", "banksy-lora")

def _load_model():
    global _model
    if _model is not None:
        return _model
    
    model_index = os.path.join(_model_dir, "model_index.json")
    if not os.path.exists(model_index):
        logger.error(f"[local_image] model_index.json not found: {model_index}")
        models_dir = os.path.join(os.path.dirname(__file__), "models")
        if os.path.exists(models_dir):
            logger.info(f"[local_image] Contents of models/: {os.listdir(models_dir)}")
        else:
            logger.error(f"[local_image] models/ directory not found")
        return None
    
    logger.info(f"[local_image] Loading model from {_model_dir}...")
    
    try:
        _model = StableDiffusionXLPipeline.from_pretrained(
            _model_dir,
            torch_dtype=torch.float32,
            use_safetensors=True,
            local_files_only=True
        )
        
        lora_file = os.path.join(_lora_path, "banksy-style.safetensors")
        if os.path.exists(lora_file):
            try:
                logger.info("[local_image] Loading Banksy LoRA...")
                _model.load_lora_weights(lora_file, adapter_name="banksy")
                _model.fuse_lora(adapter_names=["banksy"], lora_scale=1.0)
                logger.info("[local_image] Banksy LoRA loaded and fused (scale 1.0)")
            except Exception as lora_err:
                logger.warning(f"[local_image] LoRA load failed, trying UNet-only: {lora_err}")
                try:
                    from safetensors.torch import load_file
                    state_dict = load_file(lora_file)
                    unet_lora = {k.replace("unet.", ""): v for k, v in state_dict.items() if k.startswith("unet.")}
                    if unet_lora:
                        _model.load_lora_into_unet(unet_lora, network_alphas=None, unet=_model.unet)
                        logger.info("[local_image] Banksy LoRA loaded (UNet only)")
                    else:
                        logger.warning("[local_image] No UNet keys in LoRA, continuing without LoRA")
                except Exception as fallback_err:
                    logger.warning(f"[local_image] LoRA fallback failed, continuing without LoRA: {fallback_err}")
        else:
            logger.warning(f"[local_image] Banksy LoRA not found at {lora_file}")
        
        _model.to("cpu")
        logger.info("[local_image] Model loaded successfully")
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
        guidance = 7.5
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
