import os
import sys
import time
import logging
import yaml
import re

logging.basicConfig(level='%(asctime)s %(message)s', datefmt='%H:%M:%S')
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

def parse_bracket_format(raw: str):
    """Парсит формат: [-1, +2] или [-1,+2] или **[-1, +2]**"""
    values = []
    
    # Убираем markdown
    clean = raw.replace('**', '').replace('*', '')
    
    # Ищем все пары в квадратных скобках: [-1, +2] или [-1,+2]
    pattern = r'\[\s*([-\d.]+)\s*,\s*\+?([-\d.]+)\s*\]'
    matches = re.findall(pattern, clean)
    
    if len(matches) != 12:
        logger.warning(f"[chart] Expected 12 pairs, got {len(matches)}")
        return None
    
    for neg_str, pos_str in matches:
        try:
            neg = max(-5, min(0, float(neg_str)))
            pos = max(0, min(5, float(pos_str)))
            values.append((neg, pos))
        except ValueError:
            values.append((0.0, 0.0))
    
    return values

def parse_text_format(raw: str):
    """Парсит формат: '**Negative: -0** | **Positive: +5**' или 'Negative: -2 ... Positive: +2'"""
    values = []
    
    # Убираем markdown
    clean = raw.replace('**', '').replace('*', '')
    
    # Ищем все пары Negative/Positive
    neg_pattern = r'Negative:\s*([-\d.]+)'
    pos_pattern = r'Positive:\s*\+?([-\d.]+)'
    
    neg_matches = re.findall(neg_pattern, clean)
    pos_matches = re.findall(pos_pattern, clean)
    
    if len(neg_matches) < 12 or len(pos_matches) < 12:
        logger.warning(f"[chart] Expected 12 pairs, got {len(neg_matches)} neg, {len(pos_matches)} pos")
        return None
    
    for i in range(12):
        try:
            neg = max(-5, min(0, float(neg_matches[i])))
            pos = max(0, min(5, float(pos_matches[i])))
            values.append((neg, pos))
        except ValueError:
            values.append((0.0, 0.0))
    
    return values

def parse_inline_scores(raw: str):
    """Парсит формат: '1. Life: ... +5. 2. Freedom: ... +4.' - ищет оценки в тексте каждого параметра"""
    values = []
    
    # Убираем markdown
    clean = raw.replace('**', '').replace('*', '')
    
    # Разбиваем по номерам параметров
    sections = re.split(r'\n\d+\.\s+', clean)
    
    if len(sections) < 13:  # Первый элемент пустой или заголовок
        logger.warning(f"[chart] Expected 12 sections, got {len(sections)}")
        return None
    
    for i, section in enumerate(sections[1:13], 1):  # Пропускаем первый, берём 12
        # Ищем все числа со знаком + или -
        scores = re.findall(r'[+-]\d+', section)
        
        if len(scores) >= 1:
            # Берём последнее число как оценку (обычно в конце)
            score = int(scores[-1])
            if score > 0:
                values.append((0.0, min(5, float(score))))
            else:
                values.append((max(-5, float(score)), 0.0))
        else:
            values.append((0.0, 0.0))
    
    if all(v == (0.0, 0.0) for v in values):
        return None
    
    return values

def run_one(llm, name, prompt, news):
    logger.info(f"\n{'='*60}")
    logger.info(f"VARIANT: {name}")
    logger.info(f"{'='*60}")
    logger.info(f"--- PROMPT ---\n{prompt}\n--- END PROMPT ---")
    
    t0 = time.time()
    output = llm(prompt, max_tokens=1500, temperature=0.3)
    raw = output["choices"][0]["text"].strip()
    elapsed = time.time() - t0
    tokens = output['usage']['completion_tokens']
    
    logger.info(f"--- RAW ({tokens} tokens, {elapsed:.1f}s) ---\n{raw}\n--- END RAW ---")
    
    # Пробуем парсер для формата [-value, +value]
    values = parse_bracket_format(raw)
    
    if not values:
        # Пробуем парсер для текстового формата (с markdown)
        values = parse_text_format(raw)
    
    if not values:
        # Пробуем парсер для inline оценок
        values = parse_inline_scores(raw)
    
    if not values:
        # Fallback на JSON парсер
        json_part = raw
        if "JSON:" in raw:
            json_part = raw.split("JSON:")[-1].strip()
        elif "[[" in raw:
            last_bracket = raw.rfind("[[")
            if last_bracket != -1:
                json_part = raw[last_bracket:]
        
        values = chart_renderer.parse_values_json(json_part)
    
    if not values:
        logger.warning(f"[{name}] PARSE FAILED")
        return {
            "name": name,
            "time": elapsed,
            "tokens": tokens,
            "raw": raw,
            "net": None,
            "positive": None,
            "non_zero": None,
            "values": None,
            "failed": True
        }
    
    net = 0
    pos_count = 0
    non_zero = 0
    parsed_values = []
    
    for label, (min_val, max_val) in zip(chart_renderer.VALUES, values):
        balance = (min_val + max_val) / 2
        net += balance
        if balance > 0:
            pos_count += 1
        if abs(balance) > 0.01:
            non_zero += 1
        direction = "POS" if balance > 0 else "NEG" if balance < 0 else "NEU"
        logger.info(f"  {label:12s}: [{min_val:+.1f}, {max_val:+.1f}] → {balance:+.1f} | {direction}")
        parsed_values.append((label, min_val, max_val, balance, direction))
    
    logger.info(f"--- SUMMARY [{name}] ---")
    logger.info(f"  NET: {net:+.1f} | POSITIVE: {pos_count}/12 | NON-ZERO: {non_zero}/12")
    
    return {
        "name": name,
        "time": elapsed,
        "tokens": tokens,
        "raw": raw,
        "net": net,
        "positive": pos_count,
        "non_zero": non_zero,
        "values": parsed_values,
        "failed": False
    }

def print_comparison(results):
    logger.info(f"\n{'='*80}")
    logger.info("COMPARISON TABLE")
    logger.info(f"{'='*80}")
    logger.info(f"{'Variant':<20} {'Time':>6} {'Tokens':>7} {'NET':>8} {'POS':>5} {'NZ':>5} {'Status':>8}")
    logger.info("-" * 80)
    
    for r in results:
        if r["failed"]:
            logger.info(f"{r['name']:<20} {r['time']:>5.1f}s {r['tokens']:>7} {'FAIL':>8} {'--':>5} {'--':>5} {'FAILED':>8}")
        else:
            logger.info(f"{r['name']:<20} {r['time']:>5.1f}s {r['tokens']:>7} {r['net']:>+7.1f} {r['positive']:>4}/12 {r['non_zero']:>4}/12 {'OK':>8}")
    
    logger.info(f"\n{'='*80}")
    logger.info("DETAILED VALUES COMPARISON")
    logger.info(f"{'='*80}")
    
    header = f"{'Value':<12}"
    for r in results:
        header += f" {r['name'][:10]:>10}"
    logger.info(header)
    logger.info("-" * 80)
    
    for i, label in enumerate(chart_renderer.VALUES):
        row = f"{label:<12}"
        for r in results:
            if r["failed"] or not r["values"]:
                row += f" {'FAIL':>10}"
            else:
                _, _, _, balance, _ = r["values"][i]
                row += f" {balance:>+9.1f}"
        logger.info(row)
    
    logger.info(f"{'='*80}")

def main():
    news = os.getenv("NEWS_TEXT", "").strip()
    
    if not news:
        logger.error("NEWS_TEXT is empty")
        sys.exit(1)
    
    prompts = load_prompts()
    
    if "simple_v2" not in prompts:
        logger.error("simple_v2 not found in prompts_test.yaml")
        sys.exit(1)
    
    logger.info(f"=== TEST EVAL START ===")
    logger.info(f"News length: {len(news)} chars")
    logger.info(f"News preview: {news[:200]}...")
    
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
    
    prompt = prompts["simple_v2"].format(context=news[:1500])
    result = run_one(llm, "simple_v2", prompt, news)
    
    logger.info(f"\nTotal test time: {time.time()-t0:.1f}s")
    
    print_comparison([result])
    
    if result["failed"]:
        logger.error("TEST FAILED")
        sys.exit(1)
    
    logger.info(f"=== TEST DONE ===")

if __name__ == "__main__":
    main()
