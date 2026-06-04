import tweepy
import config
import logging
import io
logger = logging.getLogger(__name__)

def get_x_client():
    if not config.X_API_KEY: return None
    try:
        client = tweepy.Client(
            consumer_key=config.X_API_KEY,
            consumer_secret=config.X_API_SECRET,
            access_token=config.X_ACCESS_TOKEN,
            access_token_secret=config.X_ACCESS_TOKEN_SECRET
        )
        return client
    except Exception as e:
        logger.error(f"[x] Client init failed: {e}")
        return None

async def post_to_x(text: str, image_bytes: bytes = None) -> str | None:
    try:
        client = get_x_client()
        if not client: return None
        
        media_id = None
        if image_bytes:
            auth = tweepy.OAuth1UserHandler(
                config.X_API_KEY, config.X_API_SECRET,
                config.X_ACCESS_TOKEN, config.X_ACCESS_TOKEN_SECRET
            )
            api = tweepy.API(auth)
            media = api.media_upload(filename="digest.png", file=io.BytesIO(image_bytes))
            media_id = media.media_id
        
        response = client.create_tweet(text=text, media_ids=[media_id] if media_id else None)
        logger.info(f"[x] Posted: {response.data['id']}")
        return response.data['id']
    except Exception as e:
        logger.warning(f"[x] Post failed: {e}")
        return None
