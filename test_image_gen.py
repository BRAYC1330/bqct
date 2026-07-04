import os
import sys
import json
import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_DIR = "models/sdxl-turbo"
OUTPUT_DIR = "output"

STENCIL_SIZE = 512
CANVAS_SIZE = 1024
MARGIN = 256

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

def generate_stencil(pipe, prompt):
    logger.info(f"Generating stencil: {prompt[:100]}...")
    
    start = time.time()
    image = pipe(
        prompt=prompt,
        num_inference_steps=4,
        guidance_scale=0.0,
        width=STENCIL_SIZE,
        height=STENCIL_SIZE
    ).images[0]
    
    elapsed = time.time() - start
    logger.info(f"Generated in {elapsed:.1f}s")
    
    return image

def create_wall_with_stencil(stencil, output_file):
    canvas = Image.new('RGB', (CANVAS_SIZE, CANVAS_SIZE), 'white')
    
    offset = (CANVAS_SIZE - STENCIL_SIZE) // 2
    canvas.paste(stencil, (offset, offset))
    
    canvas.save(output_file, format="PNG")
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
    logger.info(f"Generating {total} images ({len(art_styles)} styles × {len(news_variations)} news variants)...")
    
    pipe = load_model()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for f in os.listdir(OUTPUT_DIR):
        fp = os.path.join(OUTPUT_DIR, f)
        if os.path.isfile(fp):
            os.remove(fp)
        elif os.path.isdir(fp):
            import shutil
            shutil.rmtree(fp)
    
    count = 0
    for art_style in art_styles:
        style_id = art_style['id']
        style_text = art_style['style']
        style_dir = os.path.join(OUTPUT_DIR, f"style_{style_id:02d}")
        
        for news_var in news_variations:
            news_id = news_var['id']
            news_name = news_var['name']
            news_text = news_var['text']
            
            full_prompt = f"{news_text}, {style_text}"
            output_file = os.path.join(style_dir, f"news_{news_id:02d}_{news_name}.png")
            
            stencil = generate_stencil(pipe, full_prompt)
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            create_wall_with_stencil(stencil, output_file)
            
            count += 1
    
    logger.info(f"✓ Generated {count} images in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()