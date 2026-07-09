import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

import config
import generator
import chart_renderer

PROMPTS = {
    "simple": """You are a UN Ethics Expert evaluating news against 12 values.

Values: Life, Freedom, Justice, Truth, Security, Prosperity, Equality, Dignity, Peace, Sustainability, Knowledge, Solidarity

For each value, give [negative, positive]:
- Negative: 0 to -5 (-5 = catastrophic)
- Positive: 0 to +5 (+5 = transformative)

Rules:
- At least 8 values must be non-zero
- Be EXPRESSIVE and BOLD
- START with JSON array immediately

Output: [[neg,pos],[neg,pos],...] (12 pairs total)

News: {context}

JSON:""",

    "definitions": """UN Ethics Expert. Evaluate news against 12 values.

VALUES: Life (survival/health), Freedom (autonomy), Justice (fairness), Truth (transparency), Security (safety/stability), Prosperity (economic wellbeing), Equality (equal opportunities), Dignity (human worth), Peace (harmony/no conflict), Sustainability (environment/future), Knowledge (education/science), Solidarity (community/mutual support).

PRINCIPLES:
- THREAT to value → negative score
- PROMOTES value → positive score
- NO EFFECT → 0
- Global impact → 4-5, Regional → 2-3, Local → 1-2

For each value: [negative (0 to -5), positive (0 to +5)].
At least 8 non-zero. Be EXPRESSIVE.

START with JSON: [[neg,pos],...] (12 pairs).

News: {context}

JSON:""",

    "expressive": """You are a UN Ethics Expert, internationally recognized philosopher, champion of universal human values. You believe every news impacts society.

Core values: Life, Freedom, Justice, Truth, Security, Prosperity, Equality, Dignity, Peace, Sustainability, Knowledge, Solidarity.

Evaluate this news against each value. For each value provide two numbers reflecting impact on humanity and its future:
- Negative impact (0 to -5, -5 = catastrophic)
- Positive impact (0 to +5, +5 = transformative)

MANDATORY RULES:
- You MUST provide at least 8 non-zero ratings
- Zero means NO IMPACT AT ALL
- Ratings must be EXPRESSIVE to capture public attention
- Be bold, not conservative

Output ONLY JSON array of 12 pairs [negative, positive]. No text.

News: {context}

JSON:""",

    "examples": """You are a UN Ethics Expert evaluating news against 12 values.

Values: Life, Freedom, Justice, Truth, Security, Prosperity, Equality, Dignity, Peace, Sustainability, Knowledge, Solidarity

For each value, give [negative, positive]:
- Negative: 0 to -5
- Positive: 0 to +5

Examples of CORRECT evaluation:
- Fed rate hikes → Prosperity: [-3, 0], Security: [-2, 0]
- War/conflict → Life: [-5, 0], Peace: [-5, 0], Dignity: [-4, 0]
- Scientific breakthrough → Knowledge: [0, +5], Life: [0, +3]
- Economic crisis → Prosperity: [-4, 0], Equality: [-3, 0]

Rules:
- At least 8 values must be non-zero
- Be EXPRESSIVE and BOLD
- START with JSON array immediately

Output: [[neg,pos],[neg,pos],...] (12 pairs total)

News: {context}

JSON:"""
}

def main():
    news = os.getenv("NEWS_TEXT", "").strip()
    variant = os.getenv("PROMPT_VARIANT", "simple").strip()
    
    if not news:
        logger.error("NEWS_TEXT is empty")
        sys.exit(1)
    
    if variant not in PROMPTS:
        logger.error(f"Unknown variant: {variant}")
        sys.exit(1)
    
    logger.info(f"=== TEST EVAL START ===")
    logger.info(f"Variant: {variant}")
    logger.info(f"News length: {len(news)} chars")
    logger.info(f"News preview: {news[:200]}...")
    
    prompt = PROMPTS[variant].format(context=news[:1500])
    
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
    output = llm(prompt, max_tokens=300, temperature=0.3)
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
    for label, (min_val, max_val) in zip(chart_renderer.VALUES, values):
        balance = (min_val + max_val) / 2
        net += balance
        if balance > 0:
            pos_count += 1
        direction = "POS" if balance > 0 else "NEG" if balance < 0 else "NEU"
        logger.info(f"  {label:12s}: [{min_val:+.1f}, {max_val:+.1f}] → {balance:+.1f} | {direction}")
    
    logger.info(f"=== SUMMARY ===")
    logger.info(f"NET: {net:+.1f}")
    logger.info(f"POSITIVE: {pos_count}/12")
    logger.info(f"=== TEST DONE ===")

if __name__ == "__main__":
    main()
