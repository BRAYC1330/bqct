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
                        raise
                except Exception as e:
                    last_err = e

                if attempt == max_attempts:
                    raise last_err from last_err

                wait = backoff ** attempt
                await asyncio.sleep(wait)
        return wrapper
    return decorator