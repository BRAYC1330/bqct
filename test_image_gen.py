import os
import sys
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = "output"
HF_API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

def generate_image(prompt, output_file):
    logger.info(f"Generating: {prompt[:100]}...")
    
    headers = {
        "Authorization": f"Bearer {os.environ.get('HF_API_TOKEN')}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 4,
            "width": 1024,
            "height": 1024
        }
    }
    
    start = time.time()
    response = requests.post(HF_API_URL, headers=headers, json=payload)
    
    if response.status_code != 200:
        logger.error(f"API Error: {response.status_code} - {response.text}")
        return False
    
    elapsed = time.time() - start
    logger.info(f"Generated in {elapsed:.1f}s")
    
    with open(output_file, 'wb') as f:
        f.write(response.content)
    
    logger.info(f"Saved: {output_file}")
    return True

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
            
            if generate_image(full_prompt, output_file):
                count += 1
    
    logger.info(f"✓ Generated {count - 1} images in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()