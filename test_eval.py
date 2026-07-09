import os
import sys
import time
import logging
import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

import config
import chart_renderer

def load_prompts():
    prompts_path = os.path.join(os.path.dirname(__file__), "prompts_test.yaml")
    try:
        with open(prompts_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            logger.error("prompts_test.yaml must be a dictionary")
            sys.exit(1)
        return data
    except Exception as e:
        logger.error(f"Failed to load prompts_test.yaml: {e}")
        sys.exit(1)

def main():
    news = os.getenv("NEWS_TEXT", "").strip()
    variant = os.getenv("PROMPT_VARIANT", "simple").strip()
    
    if not news:
        logger.error("NEWS_TEXT is empty")
        sys.exit(1)
    
    prompts = load_prompts()
    
    if variant not in prompts:
        logger.error(f"Unknown variant: {variant}")
        logger.error(f"Available: {', '.join(prompts.keys())}")
        sys.exit(1)
    
    prompt_template = prompts[variant]
    prompt = prompt_template.format(context=news[:1500])
    
    logger.info(f"=== TEST EVAL START ===")
    logger.info(f"Variant: {variant}")
    logger.info(f"News length: {len(news)} chars")
    logger.info(f"News preview: {news[:200]}...")
    
    logger.info(f"=== PROMPT ===")
    logger.info(prompt)
    logger.info(f"=== END PROMPT ===")
    
    logger.info("Loading model...")
    t0 = time.time()
    try:
        from llama_cpp import Llama
        llm = Llama(
            model_path=config.MODEL_PATH,
            n_ctx=config.MODEL_N_CTX,
            n_threads=config.MODEL_N_THREADS,
            verbose=False
        )
    except Exception as e:
        logger.error(f"Model load failed: {e}")
        sys.exit(1)
    logger.info(f"Model loaded in {time.time()-t0:.1f}s")
    
    logger.info("Generating response...")
    t0 = time.time()
    output = llm(prompt, max_tokens=500, temperature=0.3)
    raw = output["choices"][0]["text"].strip()
    logger.info(f"Generated in {time.time()-t0:.1f}s, {output['usage']['completion_tokens']} tokens")
    
    logger.info(f"=== RAW OUTPUT ===")
    logger.info(raw)
    logger.info(f"=== END RAW ===")
    
    values = chart_renderer.parse_values_json(raw)
    
    if not values:
        logger.error("PARSE FAILED")
        sys.exit(1)
    
    logger.info(f"=== PARSED VALUES ===")
    net = 0
    pos_count = 0
    non_zero = 0
    for label, (min_val, max_val) in zip(chart_renderer.VALUES, values):
        balance = (min_val + max_val) / 2
        net += balance
        if balance > 0:
            pos_count += 1
        if abs(balance) > 0.01:
            non_zero += 1
        direction = "POS" if balance > 0 else "NEG" if balance < 0 else "NEU"
        logger.info(f"  {label:12s}: [{min_val:+.1f}, {max_val:+.1f}] → {balance:+.1f} | {direction}")
    
    logger.info(f"=== SUMMARY ===")
    logger.info(f"NET: {net:+.1f}")
    logger.info(f"POSITIVE: {pos_count}/12")
    logger.info(f"NON-ZERO: {non_zero}/12")
    logger.info(f"=== TEST DONE ===")

if __name__ == "__main__":
    main()
