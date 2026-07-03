import os
import sys
import torch
from diffusers import StableDiffusionXLPipeline
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_DIR = "models/sdxl-turbo"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "test_output.png")

def load_model():
    logger.info("Loading SDXL-Turbo model...")
    model = StableDiffusionXLPipeline.from_pretrained(
        MODEL_DIR,
        torch_dtype=torch.float32,
        use_safetensors=True,
        local_files_only=True
    )
    model.to("cpu")
    logger.info("Model loaded successfully")
    return model

def generate_image(pipe, news_context, style_prompt):
    full_prompt = f"{news_context}, {style_prompt}"
    logger.info(f"Full prompt: {full_prompt = f"Banksy stencil of {news_object}, black silhouette on white wall, minimalist"}")
    
    start = time.time()
    image = pipe(
        prompt=full_prompt,
        num_inference_steps=4,
        guidance_scale=0.0,
        width=1024,
        height=1024
    ).images[0]
    
    elapsed = time.time() - start
    logger.info(f"Generated in {elapsed:.1f}s")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for f in os.listdir(OUTPUT_DIR):
        os.remove(os.path.join(OUTPUT_DIR, f))
    
    image.save(OUTPUT_FILE, format="PNG")
    logger.info(f"Saved: {OUTPUT_FILE}")

def main():
    if len(sys.argv) < 3:
        logger.error("Usage: python test_image_gen.py <news_context> <style_prompt>")
        sys.exit(1)
    
    news_context = sys.argv[1]
    style_prompt = sys.argv[2]
    
    pipe = load_model()
    generate_image(pipe, news_context, style_prompt)

if __name__ == "__main__":
    main()
