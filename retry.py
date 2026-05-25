import asyncio
import logging
import httpx
from functools import wraps

logger = logging.getLogger(__name__)

def retry_async(max_attempts=3, backoff=1.5):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except (httpx.RequestError, TimeoutError, OSError) as e:
                    last_err = e
                except httpx.HTTPStatusError as e:
                    if 500 <= e.response.status_code < 600:
                        last_err = e
                    else:
                        logger.error(f"[RETRY] {func.__name__} client error {e.response.status_code}, aborting")
                        raise
                except Exception as e:
                    last_err = e

                if attempt == max_attempts:
                    logger.error(f"[RETRY] {func.__name__} failed after {max_attempts} attempts: {repr(last_err)}")
                    raise last_err from last_err

                wait = backoff ** attempt
                logger.warning(f"[RETRY] {func.__name__} failed (attempt {attempt}/{max_attempts}), retrying in {wait:.1f}s")
                await asyncio.sleep(wait)
        return wrapper
    return decorator
