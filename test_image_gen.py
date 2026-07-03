import os
import sys
import json
import torch
from diffusers import StableDiffusionXLPipeline
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_DIR = "models/sdxl-turbo"
OUTPUT_DIR = "output"

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

def generate_image(pipe, prompt, output_file):
    logger.info(f"Generating: {prompt[:100]}...")
    
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
    
    image.save(output_file, format="PNG")
    logger.info(f"Saved: {output_file}")

def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python test_image_gen.py <prompts_file.json>")
        sys.exit(1)
    
    prompts_file = sys.argv[1]
    
    with open(prompts_file, 'r') as f:
        data = json.load(f)
    
    news_context = data['news_context']
    variations = data['variations']
    
    logger.info(f"Generating {len(variations)} images...")
    
    pipe = load_model()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for f in os.listdir(OUTPUT_DIR):
        os.remove(os.path.join(OUTPUT_DIR, f))
    
    for variation in variations:
        var_id = variation['id']
        style = variation['style']
        
        full_prompt = f"{news_context}, {style}"
        output_file = os.path.join(OUTPUT_DIR, f"test_{var_id:02d}.png")
        
        generate_image(pipe, full_prompt, output_file)
    
    logger.info(f"✓ Generated {len(variations)} images in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()
