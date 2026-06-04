import config
import logging
import asyncio
import tempfile
import os
import json
import httpx
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
            
            all_cookies = json.loads(config.X_COOKIES)
            logger.info(f"[x] Loaded {len(all_cookies)} cookies from JSON")
            
            skip_cookies = ['_twitter_sess', 'att', 'auth_multi']
            httpx_cookies = httpx.Cookies()
            for cookie in all_cookies:
                name = cookie.get('name')
                value = cookie.get('value')
                domain = cookie.get('domain', '.x.com')
                path = cookie.get('path', '/')
                if name in skip_cookies:
                    logger.info(f"[x] Skipping problematic cookie: {name}")
                    continue
                if name and value:
                    httpx_cookies.set(name, value, domain=domain, path=path)
                    logger.info(f"[x] Added cookie: {name} (len={len(value)})")
            
            client.set_cookies(httpx_cookies)
            logger.info(f"[x] Cookies set in twikit client")
            
            try:
                user = await client.get_user_by_screen_name(config.X_USERNAME)
                if user:
                    logger.info(f"[x] Session valid for @{user.screen_name}")
            except Exception as e:
                logger.warning(f"[x] user validation failed (will try posting): {type(e).__name__}: {repr(e)}")
            
            _x_client = client
            return client
            
        except Exception as e:
            logger.error(f"[x] Twikit init failed: {type(e).__name__}: {repr(e)}")
            return None

async def post_to_x_via_httpx(text: str, image_bytes: bytes = None) -> str | None:
    logger.info(f"[x-httpx] Attempting direct HTTP post...")
    try:
        all_cookies = json.loads(config.X_COOKIES)
        cookies = {}
        for cookie in all_cookies:
            name = cookie.get('name')
            value = cookie.get('value')
            if name in ['auth_token', 'ct0']:
                cookies[name] = value
        
        if 'auth_token' not in cookies or 'ct0' not in cookies:
            logger.error("[x-httpx] Missing auth_token or ct0")
            return None
        
        headers = {
            'authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
            'x-csrf-token': cookies['ct0'],
            'x-twitter-auth-type': 'OAuth2Session',
            'x-twitter-active-user': 'yes',
            'x-twitter-client-language': 'en',
            'content-type': 'application/x-www-form-urlencoded',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        async with httpx.AsyncClient(cookies=cookies, headers=headers, timeout=30) as client:
            payload = {
                'variables': json.dumps({
                    'tweet_text': text,
                    'dark_request': False,
                    'media': {'media_entities': [], 'possibly_sensitive': False},
                    'semantic_annotation_ids': []
                }),
                'features': json.dumps({
                    'tweetypie_unmention_optimization_enabled': True,
                    'responsive_web_edit_tweet_api_enabled': True,
                    'graphql_is_translatable_rweb_tweet_is_translatable_enabled': True,
                    'view_counts_everywhere_api_enabled': True,
                    'longform_notetweets_consumption_enabled': True,
                    'responsive_web_twitter_article_tweet_consumption_enabled': False,
                    'tweet_awards_web_tipping_enabled': False,
                    'longform_notetweets_rich_text_read_enabled': True,
                    'longform_notetweets_inline_media_enabled': True,
                    'responsive_web_graphql_exclude_directive_enabled': True,
                    'verified_phone_label_enabled': False,
                    'freedom_of_speech_not_reach_fetch_enabled': True,
                    'standardized_nudges_misinfo': True,
                    'tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled': True,
                    'responsive_web_media_download_video_enabled': False,
                    'responsive_web_graphql_skip_user_profile_image_extensions_enabled': False,
                    'responsive_web_graphql_timeline_navigation_enabled': True,
                    'responsive_web_enhance_cards_enabled': False
                }),
                'queryId': 'znCbFMaVoZUEByMe7qVJWw'
            }
            
            r = await client.post('https://x.com/i/api/graphql/znCbFMaVoZUEByMe7qVJWw/CreateTweet', data=payload)
            logger.info(f"[x-httpx] Response: {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                tweet_id = data.get('data', {}).get('create_tweet', {}).get('tweet_results', {}).get('result', {}).get('rest_id')
                if tweet_id:
                    logger.info(f"[x-httpx] Tweet created: {tweet_id}")
                    return str(tweet_id)
                logger.warning(f"[x-httpx] No tweet_id in response: {data}")
            else:
                logger.error(f"[x-httpx] Failed: {r.text[:500]}")
            return None
    except Exception as e:
        logger.error(f"[x-httpx] Failed: {type(e).__name__}: {repr(e)}")
        return None

async def post_to_x(text: str, image_bytes: bytes = None) -> str | None:
    logger.info(f"[x] === POST_TO_X START ===")
    logger.info(f"[x] Text length: {len(text)} chars")
    logger.info(f"[x] Has image: {image_bytes is not None} ({len(image_bytes) if image_bytes else 0} bytes)")
    
    try:
        client = await get_x_client()
        if client:
            media_ids = []
            if image_bytes:
                logger.info(f"[x] Uploading image ({len(image_bytes)} bytes)...")
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    f.write(image_bytes)
                    temp_path = f.name
                try:
                    media_id = await client.upload_media(temp_path)
                    media_ids.append(media_id)
                    logger.info(f"[x] Image uploaded: media_id={media_id}")
                except Exception as e:
                    logger.warning(f"[x] Image upload failed: {type(e).__name__}: {repr(e)}")
                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
            
            logger.info(f"[x] Creating tweet via twikit...")
            try:
                tweet = await client.create_tweet(text=text, media_ids=media_ids if media_ids else None)
                tweet_id = tweet.id if hasattr(tweet, 'id') else None
                if tweet_id:
                    tweet_url = f"https://x.com/{config.X_USERNAME}/status/{tweet_id}"
                    logger.info(f"[x] Tweet created successfully!")
                    logger.info(f"[x] Tweet ID: {tweet_id}")
                    logger.info(f"[x] Tweet URL: {tweet_url}")
                    return str(tweet_id)
            except Exception as e:
                logger.warning(f"[x] Twikit create_tweet failed: {type(e).__name__}: {repr(e)}")
    except Exception as e:
        logger.warning(f"[x] Twikit failed: {type(e).__name__}: {repr(e)}")
    
    logger.info(f"[x] Falling back to direct HTTP request...")
    return await post_to_x_via_httpx(text, None)
