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

def generate_image(pipe, prompt):
    logger.info(f"Prompt: {prompt}")
    
    start = time.time()
    image = pipe(
        prompt=prompt,
        num_inference_steps=4,
        guidance_scale=0.0,
        width=512,
        height=512
    ).images[0]
    
    elapsed = time.time() - start
    logger.info(f"Generated in {elapsed:.1f}s")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for f in os.listdir(OUTPUT_DIR):
        os.remove(os.path.join(OUTPUT_DIR, f))
    
    image.save(OUTPUT_FILE, format="PNG")
    logger.info(f"Saved: {OUTPUT_FILE}")

def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python test_image_gen.py <prompt>")
        sys.exit(1)
    
    prompt = sys.argv[1]
    
    pipe = load_model()
    generate_image(pipe, prompt)

if __name__ == "__main__":
    main()
