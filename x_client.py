import tweepy
import config
import logging
import io
logger = logging.getLogger(__name__)

def get_x_client():
    if not config.X_API_KEY:
        logger.warning("[x] X_API_KEY is empty")
        return None
    try:
        client = tweepy.Client(
            consumer_key=config.X_API_KEY,
            consumer_secret=config.X_API_SECRET,
            access_token=config.X_ACCESS_TOKEN,
            access_token_secret=config.X_ACCESS_TOKEN_SECRET
        )
        logger.info("[x] Tweepy Client initialized (v2 API)")
        return client
    except Exception as e:
        logger.error(f"[x] Client init failed: {type(e).__name__}: {repr(e)}")
        return None

def get_x_api_v1():
    if not config.X_API_KEY:
        return None
    try:
        auth = tweepy.OAuth1UserHandler(
            config.X_API_KEY, config.X_API_SECRET,
            config.X_ACCESS_TOKEN, config.X_ACCESS_TOKEN_SECRET
        )
        api = tweepy.API(auth)
        logger.info("[x] Tweepy API v1.1 initialized (for media upload)")
        return api
    except Exception as e:
        logger.error(f"[x] API v1 init failed: {type(e).__name__}: {repr(e)}")
        return None

async def post_to_x(text: str, image_bytes: bytes = None) -> str | None:
    try:
        client = get_x_client()
        if not client:
            logger.warning("[x] No client available, aborting")
            return None
        
        media_id = None
        if image_bytes:
            logger.info(f"[x] Uploading image ({len(image_bytes)} bytes)...")
            api = get_x_api_v1()
            if api:
                try:
                    media = api.media_upload(filename="digest.png", file=io.BytesIO(image_bytes))
                    media_id = media.media_id
                    logger.info(f"[x] Image uploaded: media_id={media_id}")
                except Exception as e:
                    logger.warning(f"[x] Image upload failed (posting without image): {type(e).__name__}: {repr(e)}")
                    media_id = None
            else:
                logger.warning("[x] API v1 not available, posting without image")
        
        logger.info(f"[x] Creating tweet (text={len(text)} chars, media_id={media_id})...")
        try:
            response = client.create_tweet(
                text=text,
                media_ids=[media_id] if media_id else None
            )
            tweet_id = response.data.get("id") if response.data else None
            if tweet_id:
                logger.info(f"[x] Tweet created successfully: id={tweet_id}")
                return tweet_id
            else:
                logger.warning(f"[x] create_tweet returned no id: {response}")
                return None
        except tweepy.TweepyException as e:
            error_details = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_details = e.response.text[:500]
                except:
                    error_details = str(e.response.status_code)
            logger.error(f"[x] Tweet creation failed: {type(e).__name__}: {repr(e)} | Details: {error_details}")
            return None
    except Exception as e:
        logger.error(f"[x] post_to_x unexpected error: {type(e).__name__}: {repr(e)}")
        return None
