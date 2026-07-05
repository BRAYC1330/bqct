import os
import sys
import json
import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image, ImageEnhance
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_DIR = "models/sdxl-turbo"
LORA_DIR = "lora"
LORA_PATH = os.path.join(LORA_DIR, "Banksy Style.safetensors")
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
    
    if os.path.exists(LORA_PATH):
        logger.info(f"Attempting to load LoRA from {LORA_PATH}...")
        try:
            model.load_lora_weights(LORA_PATH)
            logger.info("LoRA loaded successfully")
        except Exception as e:
            logger.warning(f"LoRA incompatible or broken: {e}")
            logger.warning("Falling back to base SDXL-Turbo model")
    else:
        logger.warning(f"LoRA file not found at {LORA_PATH}, using base model only")
    
    logger.info("Model loaded successfully")
    return model

def remove_yellow_tint(image):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.2)
    
    image = image.convert('L')
    image = image.convert('RGB')
    
    return image

def generate_image(pipe, prompt, output_file):
    logger.info(f"Generating: {prompt[:100]}...")
    
    start = time.time()
    image = pipe(
        prompt=prompt,
        num_inference_steps=5,
        guidance_scale=1.0,
        width=1024,
        height=1024
    ).images[0]
    
    elapsed = time.time() - start
    logger.info(f"Generated in {elapsed:.1f}s")
    
    image = remove_yellow_tint(image)
    
    image.save(output_file, format="PNG")
    logger.info(f"Saved: {output_file}")

def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python test_image_gen.py <prompts_file.json>")
        sys.exit(1)
    
    prompts_file = sys.argv[1]
    
    with open(prompts_file, 'r') as f:
        data = json.load(f)
    
    news_variations = data['news_variations']
    art_styles = data['art_styles']
    
    total = len(art_styles) * len(news_variations)
    logger.info(f"Generating {total} images...")
    
    pipe = load_model()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for f in os.listdir(OUTPUT_DIR):
        fp = os.path.join(OUTPUT_DIR, f)
        if os.path.isfile(fp):
            os.remove(fp)
    
    count = 1
    for art_style in art_styles:
        style_text = art_style['style']
        
        for news_var in news_variations:
            news_text = news_var['text']
            
            full_prompt = f"{news_text}, {style_text}"
            output_file = os.path.join(OUTPUT_DIR, f"image_{count:02d}.png")
            
            generate_image(pipe, full_prompt, output_file)
            count += 1
    
    logger.info(f"✓ Generated {count - 1} images in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()
