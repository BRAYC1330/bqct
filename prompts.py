import os
import pathlib
import yaml
import logging
import re
logger = logging.getLogger(__name__)
PROMPTS_PATH = pathlib.Path(__file__).parent / "prompts.yaml"
with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
    _prompts = yaml.safe_load(f)
def load_prompt(key: str, **kwargs) -> str:
    template = str(_prompts.get(key, ""))
    if not template:
        logger.warning(f"[prompts] Key '{key}' not found")
        return ""
    safe_kwargs = {k: str(v) if v is not None else "" for k, v in kwargs.items()}
    for ph in re.findall(r'\{(\w+)\}', template):
        if ph not in safe_kwargs:
            safe_kwargs[ph] = ""
    try:
        return template.format(**safe_kwargs)
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"[prompts] Format error for '{key}': {e}")
        return template