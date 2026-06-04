import config
import logging
import asyncio
import tempfile
import os
import json
from twikit import Client
logger = logging.getLogger(__name__)

_x_client = None
_x_client_lock = asyncio.Lock()

async def get_x_client():
    global _x_client
    async with _x_client_lock:
        if _x_client is not None:
            return _x_client
        if not config.X_USERNAME:
            logger.warning("[x] X_USERNAME not set")
            return None
        if not config.X_COOKIES:
            logger.warning("[x] X_COOKIES not set")
            return None
        try:
            logger.info(f"[x] Initializing twikit Client for @{config.X_USERNAME}...")
            client = Client('en-US')
            cookies = json.loads(config.X_COOKIES)
            client.set_cookies(cookies)
            try:
                user = await client.user()
                logger.info(f"[x] ✅ Session valid for @{user.screen_name}")
            except Exception as e:
                logger.error(f"[x] Session invalid: {type(e).__name__}: {repr(e)}")
                return None
            _x_client = client
            return client
        except Exception as e:
            logger.error(f"[x] Twikit init failed: {type(e).__name__}: {repr(e)}")
            return None

async def post_to_x(text: str, image_bytes: bytes = None) -> str | None:
    logger.info(f"[x] === POST_TO_X START ===")
    logger.info(f"[x] Text length: {len(text)} chars")
    logger.info(f"[x] Has image: {image_bytes is not None} ({len(image_bytes) if image_bytes else 0} bytes)")
    try:
        client = await get_x_client()
        if not client:
            logger.warning("[x] No client available, aborting")
            return None
        media_ids = []
        if image_bytes:
            logger.info(f"[x] Uploading image ({len(image_bytes)} bytes)...")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(image_bytes)
                temp_path = f.name
            try:
                media_id = await client.upload_media(temp_path)
                media_ids.append(media_id)
                logger.info(f"[x] ✅ Image uploaded: media_id={media_id}")
            except Exception as e:
                logger.warning(f"[x] Image upload failed (posting without image): {type(e).__name__}: {repr(e)}")
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        logger.info(f"[x] Creating tweet...")
        tweet = await client.create_tweet(text=text, media_ids=media_ids if media_ids else None)
        tweet_id = tweet.id if hasattr(tweet, 'id') else None
        if tweet_id:
            tweet_url = f"https://x.com/{config.X_USERNAME}/status/{tweet_id}"
            logger.info(f"[x] ✅ Tweet created successfully!")
            logger.info(f"[x] Tweet ID: {tweet_id}")
            logger.info(f"[x] Tweet URL: {tweet_url}")
            return str(tweet_id)
        logger.warning(f"[x] create_tweet returned no id: {tweet}")
        return None
    except Exception as e:
        logger.error(f"[x] post_to_x failed: {type(e).__name__}: {repr(e)}")
        return None
