import re
import logging

logger = logging.getLogger(__name__)

def clean_for_llm(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+', '', text)
    text = re.sub(r'(!t|!c)', '', text, flags=re.I)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[\*\_~`>|]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def count_graphemes(text: str) -> int:
    return len(text) if text else 0

def count_tokens(text: str, llm) -> int:
    if hasattr(llm, "tokenize"):
        return len(llm.tokenize(text.encode('utf-8')))
    return len(text) // 3

def truncate_text(text: str, max_len: int, sig: str = "") -> str:
    safe_len = max_len - len(sig)
    if len(text) <= safe_len:
        return text
    truncated = text[:safe_len]
    last_dot = truncated.rfind(".")
    return truncated[:last_dot+1].strip() if last_dot != -1 else truncated.rstrip()

def is_english(text: str) -> bool:
    if not text:
        return False
    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars:
        return True
    return (sum(1 for c in alpha_chars if c.isascii()) / len(alpha_chars)) >= 0.7