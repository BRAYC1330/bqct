import re
import logging

logger = logging.getLogger(__name__)

def clean_for_llm(text: str) -> str:
    if not text: return ""
    text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+', '', text)
    text = re.sub(r'(!t|!c)', '', text, flags=re.I)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[\*\_~`>|]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def count_graphemes(text: str) -> int:
    if not text: return 0
    return len(text.encode('utf-8').decode('utf-8', errors='ignore'))

def count_tokens(text: str, llm) -> int:
    if hasattr(llm, "tokenize"):
        return len(llm.tokenize(text.encode('utf-8')))
    return len(text) // 3

def compress_numbers(text: str) -> str:
    if not text: return ""
    text = re.sub(r'\bthousands?\b', 'K', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmillions?\b', 'M', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbillions?\b', 'B', text, flags=re.IGNORECASE)
    text = re.sub(r'\btrillions?\b', 'T', text, flags=re.IGNORECASE)
    text = re.sub(r'\bquintillions?\b', 'Q', text, flags=re.IGNORECASE)
    return text

def truncate_text(text: str, max_len: int, sig: str = "") -> str:
    safe_len = max_len - len(sig)
    if len(text) <= safe_len: return text
    
    truncated = text[:safe_len]
    last_safe_dot = -1
    
    for i in range(len(truncated) - 1, 0, -1):
        if truncated[i] == '.':
            prev_char = truncated[i-1] if i > 0 else ''
            next_char = truncated[i+1] if i+1 < len(truncated) else ''
            if prev_char.isdigit(): continue
            if next_char.islower(): continue
            if i < 100: continue
            last_safe_dot = i
            break
            
    if last_safe_dot > 100:
        return truncated[:last_safe_dot + 1].strip()
        
    last_space = truncated.rfind(' ')
    if last_space > safe_len * 0.8:
        return truncated[:last_space].strip()
        
    return truncated.rstrip()

def is_english(text: str) -> bool:
    if not text: return False
    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars: return True
    return (sum(1 for c in alpha_chars if c.isascii()) / len(alpha_chars)) >= 0.7
