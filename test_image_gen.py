import os
import sys
import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image
import io
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_DIR = "models/sdxl-base"
OUTPUT_FILE = "test_output.png"

def load_model():
    logger.info("Loading SDXL model...")
    model = StableDiffusionXLPipeline.from_pretrained(
        MODEL_DIR,
        torch_dtype=torch.float32,
        use_safetensors=True,
        local_files_only=True
    )
    model.to("cpu")
    logger.info("Model loaded successfully")
    return model

def generate_image(pipe, style_prompt, news_context):
    full_prompt = f"{style_prompt} {news_context}"
    logger.info(f"Full prompt: {full_prompt}")
    
    negative_prompt = "colorful, rainbow, bright colors, full wall coverage, crowd, complex composition, detailed background"
    
    start = time.time()
    image = pipe(
        prompt=full_prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=10,
        guidance_scale=7.5,
        width=1024,
        height=1024
    ).images[0]
    
    elapsed = time.time() - start
    logger.info(f"Generated in {elapsed:.1f}s")
    
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    
    with open(OUTPUT_FILE, "wb") as f:
        f.write(buffer.getvalue())
    
    logger.info(f"Saved: {OUTPUT_FILE}")

def main():
    if len(sys.argv) < 3:
        logger.error("Usage: python test_image_gen.py <style_prompt> <news_context>")
        sys.exit(1)
    
    style_prompt = sys.argv[1]
    news_context = sys.argv[2]
    
    pipe = load_model()
    generate_image(pipe, style_prompt, news_context)

if __name__ == "__main__":
    main()
