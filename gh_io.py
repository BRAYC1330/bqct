import os
import logging

logger = logging.getLogger(__name__)

def write_outputs(**kwargs):
    out_path = os.getenv("GITHUB_OUTPUT")
    if not out_path:
        return
    try:
        with open(out_path, "a", encoding="utf-8") as f:
            for k, v in kwargs.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        logger.error(f"GITHUB_OUTPUT write failed: {e}")