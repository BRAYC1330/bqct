import asyncio
import logging
import httpx
from functools import wraps
logger = logging.getLogger(__name__)
def retry_async(max_attempts=3, backoff=1.5):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except (httpx.RequestError, httpx.HTTPStatusError, TimeoutError, OSError) as e:
                    if attempt == max_attempts:
                        logger.error(f"[RETRY] {func.__name__} failed after {attempt} attempts: {repr(e)}")
                        raise
                    wait = backoff ** attempt
                    logger.warning(f"[RETRY] {func.__name__} failed (attempt {attempt}/{max_attempts}), retrying in {wait:.1f}s: {repr(e)}")
                    await asyncio.sleep(wait)
        return wrapper
    return decorator