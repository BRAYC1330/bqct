import os
import json
import logging
import httpx
from datetime import datetime, timezone
import config
from retry import retry_async
from PIL import Image
import io

logger = logging.getLogger(__name__)

@retry_async()
async def login_with_cache(client, handle, password):
    session_path = "session.json"
    if os.path.exists(session_path):
        try:
            with open(session_path) as f:
                sess = json.load(f)
            client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
            logger.info("[bsky] Session loaded from cache")
            return
        except Exception:
            pass
    r = await client.post(f"{config.BSKY_PDS_URL}/xrpc/com.atproto.server.createSession", json={"identifier": handle, "password": password})
    r.raise_for_status()
    sess = r.json()
    client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
    with open(session_path, "w") as f:
        json.dump(sess, f)
    logger.info("[bsky] New session created and cached")

@retry_async()
async def post_root(client, bot_did, text, facets=None, embed=None):
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat()}
    if facets: record["facets"] = facets
    if embed: record["embed"] = embed
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await client.post(f"{config.BSKY_PDS_URL}/xrpc/com.atproto.repo.createRecord", json=body)
    r.raise_for_status()
    return r.json()

@retry_async()
async def post_reply(client, bot_did, text, root_uri, root_cid, parent_uri, parent_cid, facets=None, embed=None):
    reply = {"root": {"uri": root_uri, "cid": root_cid}, "parent": {"uri": parent_uri, "cid": parent_cid}}
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat(), "reply": reply}
    if facets: record["facets"] = facets
    if embed: record["embed"] = embed
    body = {"repo": bot_did, "collection": "app.bsky.feed.post", "record": record}
    r = await client.post(f"{config.BSKY_PDS_URL}/xrpc/com.atproto.repo.createRecord", json=body)
    r.raise_for_status()
    return r.json()

@retry_async()
async def post_like(client, bot_did, subject_uri, subject_cid):
    record = {
        "$type": "app.bsky.feed.like",
        "subject": {"$type": "com.atproto.repo.strongRef", "uri": subject_uri, "cid": subject_cid},
        "createdAt": datetime.now(timezone.utc).isoformat()
    }
    body = {"repo": bot_did, "collection": "app.bsky.feed.like", "record": record}
    r = await client.post(f"{config.BSKY_PDS_URL}/xrpc/com.atproto.repo.createRecord", json=body)
    r.raise_for_status()
    return r.json()

@retry_async()
async def fetch_thread_chain(client, uri):
    r = await client.get(f"{config.BSKY_PDS_URL}/xrpc/app.bsky.feed.getPostThread", params={"uri": uri, "depth": 0, "parentHeight": 100})
    if r.status_code != 200:
        logger.warning(f"[bsky] Thread fetch failed: {r.status_code}")
        return None
    data = r.json()
    thread = data.get("thread", {})
    post = thread.get("post", {})
    record = post.get("record", {})
    reply_ref = record.get("reply", {})
    root_ref = reply_ref.get("root", {}) if reply_ref else {}
    parent_ref = reply_ref.get("parent", {}) if reply_ref else {}
    root_uri = root_ref.get("uri") if root_ref.get("uri") else uri
    root_cid = root_ref.get("cid") if root_ref.get("cid") else post.get("cid", "")
    parent_cid_ref = parent_ref.get("cid", "") if parent_ref else ""
    chain = []
    current = thread
    while current and isinstance(current, dict):
        p = current.get("post")
        if p: chain.append(p)
        current = current.get("parent")
    chain = list(reversed(chain))
    root_post = chain[0] if chain else post
    root_text = root_post.get("record", {}).get("text", "")
    return {
        "root_uri": root_uri, "root_cid": root_cid, "root_text": root_text,
        "parent_cid": parent_cid_ref, "cid": post.get("cid", ""), "chain": chain
    }

@retry_async()
async def fetch_notifications(client, limit=100, seen_at=None):
    params = {"limit": limit}
    if seen_at and seen_at not in ("{}", "null", "none"):
        params["seen_at"] = seen_at
    r = await client.get(f"{config.BSKY_PDS_URL}/xrpc/app.bsky.notification.listNotifications", params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("notifications", [])

def extract_embed_text(embed):
    texts = []
    if not embed: return ""
    et = embed.get("$type", "")
    if et == "app.bsky.embed.images":
        for img in embed.get("images", []):
            if img.get("alt"): texts.append(img["alt"])
    elif et == "app.bsky.embed.external":
        ext = embed.get("external", {})
        if ext.get("title"): texts.append(ext["title"])
        if ext.get("description"): texts.append(ext["description"])
    elif et == "app.bsky.embed.record":
        val = embed.get("record", {}).get("value", {})
        if val.get("text"): texts.append(val["text"])
    elif et == "app.bsky.embed.recordWithMedia":
        val = embed.get("record", {}).get("value", {})
        if val.get("text"): texts.append(val["text"])
        med = embed.get("media", {})
        if med.get("$type") == "app.bsky.embed.images":
            for img in med.get("images", []):
                if img.get("alt"): texts.append(img["alt"])
    return " ".join(texts)

async def fetch_url_content(client, url):
    try:
        from trafilatura import extract as trafilatura_extract
        parsed = httpx.URL(url)
        if parsed.netloc not in config.ALLOWED_LINK_DOMAINS: return ""
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=config.REQUEST_TIMEOUT)
        if r.status_code == 200:
            txt = trafilatura_extract(r.text, include_tables=False, include_comments=False, output_format="txt")
            if txt: return txt
    except Exception:
        pass
    return ""

async def upload_digest_image(client, image_bytes: bytes, mime: str = "image/png", alt: str = ""):
    try:
        logger.info(f"[bsky] Uploading image: {len(image_bytes)} bytes, mime={mime}")
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        logger.info(f"[bsky] Image actual size: {width}x{height}")
        max_size = 900 * 1024
        if len(image_bytes) > max_size:
            logger.info(f"[bsky] Compressing image: {len(image_bytes)} → <{max_size}")
            img = img.convert("RGB")
            for quality in [85, 75, 65]:
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                if buf.tell() <= max_size:
                    image_bytes = buf.getvalue()
                    mime = "image/jpeg"
                    logger.info(f"[bsky] Compressed to {len(image_bytes)} bytes @ quality={quality}")
                    break
            else:
                img.thumbnail((1200, 800), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70, optimize=True)
                image_bytes = buf.getvalue()
                mime = "image/jpeg"
                width, height = img.size
        url = f"{config.BSKY_PDS_URL}/xrpc/com.atproto.repo.uploadBlob"
        headers = {
            "Content-Type": mime,
            "Authorization": client.headers.get("Authorization", "")
        }
        r = await client.post(url, content=image_bytes, headers=headers, timeout=30)
        if r.status_code != 200:
            logger.warning(f"[bsky] uploadBlob failed: {r.status_code} - {r.text[:300]}")
            return None
        blob = r.json().get("blob")
        if not blob:
            logger.warning("[bsky] uploadBlob returned no blob")
            return None
        logger.info(f"[bsky] Image uploaded, blob size: {blob.get('size')}")
        return {
            "$type": "app.bsky.embed.images",
            "images": [{
                "alt": alt or "Digest visualization",
                "image": blob,
                "aspectRatio": {"width": width, "height": height}
            }]
        }
    except Exception as e:
        logger.warning(f"[bsky] Digest image upload failed: {type(e).__name__}: {e}")
        import traceback
        logger.warning(f"[bsky] Traceback: {traceback.format_exc()[:500]}")
        return None
