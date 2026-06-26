import os
import logging
import re
import asyncio
import json
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
    if not os.path.exists(model_path): return None
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=config.MODEL_N_CTX,
            n_gpu_layers=0,
            n_threads=config.MODEL_N_THREADS,
            n_batch=512,
            verbose=False
        )
        return llm
    except Exception as e:
        logger.error(f"[generator] Model load failed: {repr(e)}")
        return None

async def extract_search_intent(llm, user_query: str) -> tuple:
    prompt = load_prompt("tavily_intent", query=user_query)
    try:
        raw = _get_llm_text(await asyncio.to_thread(llm, prompt, max_tokens=config.LLM_TOKENS_INTENT, temperature=0.1))
        if "| TIME:" in raw:
            q_part, t_part = raw.split("| TIME:", 1)
            query = q_part.replace("QUERY:", "").strip().strip('"')
            time_range = t_part.strip().lower()
            if time_range not in ("day", "week", "month", "year"): time_range = ""
            return query, time_range
        return user_query, ""
    except Exception:
        return user_query, ""

async def extract_chainbase_keyword(llm, query: str, context: str) -> str:
    prompt = load_prompt("chainbase_keyword", query=query, context=context)
    try:
        raw = _get_llm_text(await asyncio.to_thread(llm, prompt, max_tokens=config.LLM_TOKENS_KEYWORD, temperature=0.1))
        kw = raw.split()[0] if raw else ""
        return re.sub(r'[^\w]', '', kw)
    except Exception:
        return ""

async def classify_intent(llm, message: str, root_topic: str) -> str:
    prompt = load_prompt("intent_check", message=message, root_topic=root_topic)
    try:
        raw = _get_llm_text(await asyncio.to_thread(llm, prompt, max_tokens=config.LLM_TOKENS_INTENT, temperature=0.1))
        return "SUBSTANTIVE" if "SUBSTANTIVE" in raw.upper() else "CASUAL"
    except Exception:
        return "SUBSTANTIVE"

async def classify_sentiment(llm, message: str, root_topic: str) -> str:
    prompt = load_prompt("sentiment_check", message=message, root_topic=root_topic)
    try:
        raw = _get_llm_text(await asyncio.to_thread(llm, prompt, max_tokens=config.LLM_TOKENS_INTENT, temperature=0.1))
        if "POSITIVE" in raw.upper(): return "POSITIVE"
        if "NEGATIVE" in raw.upper(): return "NEGATIVE"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"

async def classify_community_input(llm, message: str, root_topic: str, query: str) -> dict:
    prompt = load_prompt("community_classify_combined", message=message, root_topic=root_topic, query=query)
    try:
        raw = _get_llm_text(await asyncio.to_thread(llm, prompt, max_tokens=50, temperature=0.1))
        data = json.loads(raw)
        return {
            "intent": data.get("intent", "SUBSTANTIVE").upper(),
            "sentiment": data.get("sentiment", "NEUTRAL").upper(),
            "keyword": re.sub(r'[^\w]', '', data.get("keyword", ""))
        }
    except Exception:
        return {"intent": "SUBSTANTIVE", "sentiment": "NEUTRAL", "keyword": ""}

async def regenerate_keyword(llm, original: str, query: str, root_topic: str, tried_keywords: str = "none") -> str:
    prompt = load_prompt("keyword_regenerate", original=original, query=query, root_topic=root_topic, tried_keywords=tried_keywords)
    try:
        raw = _get_llm_text(await asyncio.to_thread(llm, prompt, max_tokens=config.LLM_TOKENS_REGEN, temperature=0.3))
        kw = raw.split()[0] if raw else ""
        return re.sub(r'[^\w]', '', kw)
    except Exception:
        return ""

async def validate_search_results(llm, query: str, sample_results: str) -> bool:
    prompt = load_prompt("validate_search", query=query, sample=sample_results)
    try:
        raw = _get_llm_text(await asyncio.to_thread(llm, prompt, max_tokens=3, temperature=0.1))
        return "RELEVANT" in raw.upper()
    except Exception:
        return True

async def get_answer(llm, context: str, user_query: str, max_chars: int = config.MAX_COMMENT_CHARS, temperature: float = config.LLM_TEMP_STANDARD, prompt_key: str = "community_reply", **kwargs) -> str:
    prompt_skeleton = load_prompt(prompt_key, query=user_query, max_chars=max_chars, context=context, **kwargs)
    full_prompt = f"{context}\n{prompt_skeleton}"
    try:
        output = await asyncio.to_thread(llm, full_prompt, max_tokens=config.LLM_TOKENS_REPLY, temperature=temperature)
        return _get_llm_text(output)
    except Exception:
        return ""