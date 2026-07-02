import os
import torch
from diffusers import FluxPipeline
from huggingface_hub import login, list_repo_files
from PIL import Image
import io
import logging
import config

logger = logging.getLogger(__name__)

_model = None
_model_dir = os.path.join(os.path.dirname(__file__), "models", "flux-lite-8b")

def _load_model():
    global _model
    if _model is not None:
        return _model
    
    gguf_file = os.path.join(_model_dir, "flux.1-lite-8B-Q4_K_M.gguf")
    
    logger.info(f"[local_image] === MODEL LOADING DEBUG ===")
    logger.info(f"[local_image] Model directory: {_model_dir}")
    logger.info(f"[local_image] Expected GGUF file: {gguf_file}")
    
    if not os.path.exists(gguf_file):
        logger.error(f"[local_image] GGUF file not found: {gguf_file}")
        models_dir = os.path.join(os.path.dirname(__file__), "models")
        if os.path.exists(models_dir):
            logger.info(f"[local_image] Contents of models/: {os.listdir(models_dir)}")
            if os.path.exists(_model_dir):
                logger.info(f"[local_image] Contents of {_model_dir}: {os.listdir(_model_dir)}")
        else:
            logger.error(f"[local_image] models/ directory not found")
        return None
    
    file_size = os.path.getsize(gguf_file)
    logger.info(f"[local_image] GGUF file exists, size: {file_size} bytes ({file_size / (1024**3):.2f} GB)")
    
    try:
        hf_token = os.getenv("HF_API_TOKEN", "").strip() or None
        
        logger.info(f"[local_image] HF_API_TOKEN set: {bool(hf_token)}")
        if hf_token:
            logger.info(f"[local_image] HF_API_TOKEN length: {len(hf_token)}")
            logger.info("[local_image] Logging in to HuggingFace Hub...")
            login(token=hf_token)
        else:
            logger.warning("[local_image] HF_API_TOKEN not found")
        
        logger.info("[local_image] Listing repo files for verification...")
        try:
            kwargs = {'token': hf_token} if hf_token else {}
            files = list_repo_files('hum-ma/flux.1-lite-8B-GGUF', **kwargs)
            logger.info(f"[local_image] Repo contains {len(files)} files")
            gguf_files = [f for f in files if f.endswith('.gguf')]
            logger.info(f"[local_image] GGUF files in repo: {gguf_files}")
        except Exception as e:
            logger.warning(f"[local_image] Failed to list repo files: {e}")
        
        logger.info("[local_image] Attempting to load FluxPipeline from GGUF...")
        logger.info(f"[local_image] Using torch_dtype: torch.float32")
        logger.info(f"[local_image] Token provided: {bool(hf_token)}")
        
        _model = FluxPipeline.from_single_file(
            gguf_file,
            torch_dtype=torch.float32,
            token=hf_token
        )
        
        logger.info("[local_image] Pipeline loaded successfully, moving to CPU...")
        _model.to("cpu")
        logger.info("[local_image] FLUX model loaded and ready")
        logger.info(f"[local_image] === END MODEL LOADING DEBUG ===")
        return _model
        
    except Exception as e:
        logger.error(f"[local_image] === MODEL LOADING FAILED ===")
        logger.error(f"[local_image] Error type: {type(e).__name__}")
        logger.error(f"[local_image] Error message: {str(e)}")
        import traceback
        logger.error(f"[local_image] Full traceback:")
        logger.error(traceback.format_exc())
        logger.error(f"[local_image] === END ERROR DEBUG ===")
        return None

def generate_image(prompt: str, negative_prompt: str = "", width: int = 1024, height: int = 1024) -> bytes | None:
    try:
        pipe = _load_model()
        if pipe is None:
            logger.warning("[local_image] Model not loaded")
            return None
        
        steps = config.IMAGE_INFERENCE_STEPS
        guidance = 3.5
        logger.info(f"[local_image] === IMAGE GENERATION DEBUG ===")
        logger.info(f"[local_image] Prompt: {prompt[:200]}...")
        logger.info(f"[local_image] Negative prompt: {negative_prompt[:100] if negative_prompt else 'None'}")
        logger.info(f"[local_image] Steps: {steps}, Guidance: {guidance}")
        logger.info(f"[local_image] Size: {width}x{height}")
        
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
        
        logger.info("[local_image] Starting inference...")
        image = pipe(
            prompt=prompt,
            negative_prompt=enhanced_negative,
            num_inference_steps=steps,
            guidance_scale=guidance,
            width=width,
            height=height
        ).images[0]
        
        logger.info("[local_image] Inference complete, encoding image...")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        
        if buffer.tell() > 900 * 1024:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85, optimize=True)
        
        image_bytes = buffer.getvalue()
        logger.info(f"[local_image] Generated: {len(image_bytes)} bytes ({len(image_bytes) / 1024:.2f} KB)")
        logger.info(f"[local_image] === END GENERATION DEBUG ===")
        return image_bytes
        
    except Exception as e:
        logger.warning(f"[local_image] Generation failed: {type(e).__name__}: {e}")
        import traceback
        logger.warning(f"[local_image] Traceback: {traceback.format_exc()[:1000]}")
        return None
