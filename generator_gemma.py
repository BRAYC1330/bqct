import os
import logging
import re
from llama_cpp import Llama
import config
from prompts import load_prompt
logger = logging.getLogger(__name__)

def get_model():
    model_path = config.GEMMA_MODEL_PATH
    if not os.path.exists(model_path):
        logger.error(f"[gemma] Model not found: {model_path}")
        return None
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=config.MODEL_N_CTX,
            n_gpu_layers=0,
            n_threads=config.MODEL_N_THREADS,
            n_batch=512,
            verbose=False,
            chat_format="gemma"
        )
        logger.info(f"[gemma] Model loaded: {os.path.basename(model_path)}")
        return llm
    except Exception as e:
        logger.error(f"[gemma] Model load failed: {repr(e)}")
        return None

def _call(llm, prompt: str, max_tokens: int, temperature: float) -> str:
    try:
        response = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.warning(f"[gemma] Call failed: {type(e).__name__}: {e}")
        return ""

def extract_search_intent(llm, user_query: str) -> tuple:
    prompt = load_prompt("tavily_intent", query=user_query)
    raw = _call(llm, prompt, config.LLM_TOKENS_INTENT, 0.1)
    if "| TIME:" in raw:
        q_part, t_part = raw.split("| TIME:", 1)
        query = q_part.replace("QUERY:", "").strip().strip('"')
        time_range = t_part.strip().lower()
        if time_range not in ("day", "week", "month", "year"):
            time_range = ""
        return query, time_range
    return user_query, ""

def extract_chainbase_keyword(llm, query: str, context: str) -> str:
    prompt = load_prompt("chainbase_keyword", query=query, context=context)
    raw = _call(llm, prompt, config.LLM_TOKENS_KEYWORD, 0.1)
    kw = raw.strip().split()[0] if raw.strip() else ""
    return re.sub(r'[^\w]', '', kw)

def classify_intent(llm, message: str, root_topic: str) -> str:
    prompt = load_prompt("intent_check", message=message, root_topic=root_topic)
    raw = _call(llm, prompt, config.LLM_TOKENS_INTENT, 0.1)
    cls = raw.strip().upper()
    return "SUBSTANTIVE" if "SUBSTANTIVE" in cls else "CASUAL"

def classify_sentiment(llm, message: str, root_topic: str) -> str:
    prompt = load_prompt("sentiment_check", message=message, root_topic=root_topic)
    raw = _call(llm, prompt, config.LLM_TOKENS_INTENT, 0.1)
    cls = raw.strip().upper()
    if "POSITIVE" in cls: return "POSITIVE"
    if "NEGATIVE" in cls: return "NEGATIVE"
    return "NEUTRAL"

def regenerate_keyword(llm, original: str, query: str, root_topic: str, tried_keywords: str = "none") -> str:
    prompt = load_prompt("keyword_regenerate", original=original, query=query, root_topic=root_topic, tried_keywords=tried_keywords)
    raw = _call(llm, prompt, config.LLM_TOKENS_REGEN, 0.3)
    kw = raw.strip().split()[0] if raw.strip() else ""
    return re.sub(r'[^\w]', '', kw)

def validate_search_results(llm, query: str, sample_results: str) -> bool:
    prompt = load_prompt("validate_search", query=query, sample=sample_results)
    raw = _call(llm, prompt, 3, 0.1)
    return "RELEVANT" in raw.upper()

def get_answer(llm, context: str, user_query: str, max_chars: int = config.MAX_COMMENT_CHARS, temperature: float = config.LLM_TEMP_STANDARD, prompt_key: str = "community_reply", **kwargs) -> str:
    prompt_skeleton = load_prompt(prompt_key, query=user_query, max_chars=max_chars, context=context, **kwargs)
    full_prompt = f"{context}\n{prompt_skeleton}"
    raw_text = _call(llm, full_prompt, config.LLM_TOKENS_REPLY, temperature)
    return raw_text.strip()
