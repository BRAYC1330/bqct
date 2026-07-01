import os
import logging
import re
from typing import Tuple
from llama_cpp import Llama
import config
from prompts import load_prompt

logger = logging.getLogger(__name__)

def _get_llm_text(response) -> str:
    if isinstance(response, str): return response.strip()
    if not isinstance(response, dict): return ""
    return response.get("choices", [{}])[0].get("text", "").strip()

def get_model():
    model_path = config.MODEL_PATH
    if not os.path.exists(model_path):
        logger.error(f"[generator] Model not found: {model_path}")
        return None
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=config.MODEL_N_CTX,
            n_gpu_layers=0,
            n_threads=config.MODEL_N_THREADS,
            n_batch=512,
            verbose=False
        )
        logger.info(f"[generator] Model loaded: {os.path.basename(model_path)}")
        return llm
    except Exception as e:
        logger.error(f"[generator] Model load failed: {repr(e)}")
        return None

def extract_search_intent(llm, user_query: str, full_context: str = "") -> tuple:
    context_for_prompt = full_context[:2000] if full_context else user_query
    prompt = load_prompt("tavily_intent", query=user_query, context=context_for_prompt)
    try:
        raw = _get_llm_text(llm(prompt, max_tokens=config.LLM_TOKENS_INTENT, temperature=0.1))
        if "| TIME:" in raw:
            q_part, t_part = raw.split("| TIME:", 1)
            query = q_part.replace("QUERY:", "").strip().strip('"')
            time_range = t_part.strip().lower()
            if time_range not in ("day", "week", "month", "year"):
                time_range = ""
            return query, time_range
        return user_query, ""
    except Exception as e:
        logger.warning(f"[generator] Search intent parse failed: {repr(e)}")
        return user_query, ""

def extract_chainbase_keyword(llm, query: str, context: str) -> str:
    prompt = load_prompt("chainbase_keyword", query=query, context=context)
    try:
        raw = _get_llm_text(llm(prompt, max_tokens=config.LLM_TOKENS_KEYWORD, temperature=0.1))
        kw = raw.split()[0] if raw else ""
        return re.sub(r'[^\w]', '', kw)
    except Exception as e:
        logger.warning(f"[generator] Keyword extract failed: {repr(e)}")
        return ""

def classify_intent(llm, message: str, root_topic: str) -> str:
    prompt = load_prompt("intent_check", message=message, root_topic=root_topic)
    try:
        raw = _get_llm_text(llm(prompt, max_tokens=config.LLM_TOKENS_INTENT, temperature=0.1))
        return "SUBSTANTIVE" if "SUBSTANTIVE" in raw.upper() else "CASUAL"
    except Exception as e:
        logger.warning(f"[generator] Intent classify failed: {repr(e)}")
        return "SUBSTANTIVE"

def classify_sentiment(llm, message: str, root_topic: str) -> str:
    prompt = load_prompt("sentiment_check", message=message, root_topic=root_topic)
    try:
        raw = _get_llm_text(llm(prompt, max_tokens=config.LLM_TOKENS_INTENT, temperature=0.1))
        if "POSITIVE" in raw.upper(): return "POSITIVE"
        if "NEGATIVE" in raw.upper(): return "NEGATIVE"
        return "NEUTRAL"
    except Exception as e:
        logger.warning(f"[generator] Sentiment classify failed: {repr(e)}")
        return "NEUTRAL"

def regenerate_keyword(llm, original: str, query: str, root_topic: str, tried_keywords: str = "none") -> str:
    prompt = load_prompt("keyword_regenerate", original=original, query=query, root_topic=root_topic, tried_keywords=tried_keywords)
    try:
        raw = _get_llm_text(llm(prompt, max_tokens=config.LLM_TOKENS_REGEN, temperature=0.3))
        kw = raw.split()[0] if raw else ""
        return re.sub(r'[^\w]', '', kw)
    except Exception as e:
        logger.warning(f"[generator] Keyword regen failed: {repr(e)}")
        return ""

def validate_search_results(llm, query: str, sample_results: str) -> bool:
    prompt = load_prompt("validate_search", query=query, sample=sample_results)
    try:
        raw = _get_llm_text(llm(prompt, max_tokens=3, temperature=0.1))
        return "RELEVANT" in raw.upper()
    except Exception as e:
        logger.warning(f"[generator] Search validation failed: {repr(e)}")
        return True

def get_answer(llm, context: str, user_query: str, max_chars: int = config.MAX_COMMENT_CHARS, temperature: float = config.LLM_TEMP_STANDARD, prompt_key: str = "community_reply", **kwargs) -> str:
    prompt_skeleton = load_prompt(prompt_key, query=user_query, max_chars=max_chars, context=context, **kwargs)
    if config.RAW_DEBUG:
        logger.info(f"=== [PROMPT KEY: {prompt_key}] ===")
        logger.info(prompt_skeleton)
        logger.info("=== [END PROMPT] ===")
    full_prompt = f"{context}\n{prompt_skeleton}"
    try:
        output = llm(full_prompt, max_tokens=config.LLM_TOKENS_REPLY, temperature=temperature)
        raw_text = _get_llm_text(output)
        if config.RAW_DEBUG:
            logger.info(f"=== [MODEL RAW OUTPUT] ===")
            logger.info(raw_text)
            logger.info("=== [END MODEL OUTPUT] ===")
        return raw_text
    except Exception as e:
        logger.error(f"[generator] Answer generation failed: {repr(e)}")
        return ""
