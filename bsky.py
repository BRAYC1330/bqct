import os, json, logging, httpx, base64, time
from datetime import datetime, timezone
import config
from retry import retry_async
from PIL import Image
import io

logger = logging.getLogger(__name__)

def _is_jwt_expired(token: str) -> bool:
    try:
        payload = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '=='))
        return payload.get('exp', 0) < time.time() - 300
    except: return True

@retry_async()
async def login_with_cache(client, handle, password):
    session_path = "session.json"
    if os.path.exists(session_path):
        try:
            with open(session_path) as f: sess = json.load(f)
            if not _is_jwt_expired(sess['accessJwt']):
                client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
                logger.info("[bsky] Session loaded from cache")
                return
            os.remove(session_path)
            logger.info("[bsky] Cached JWT expired, clearing")
        except Exception: pass

    r = await client.post("https://bsky.social/xrpc/com.atproto.server.createSession", json={"identifier": handle, "password": password})
    r.raise_for_status()
    sess = r.json()
    client.headers["Authorization"] = f"Bearer {sess['accessJwt']}"
    with open(session_path, "w") as f: json.dump(sess, f)
    logger.info("[bsky] New session created and cached")

@retry_async()
async def post_root(client, bot_did, text, facets=None, embed=None):
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat()}
    if facets: record["facets"] = facets
    if embed: record["embed"] = embed
    r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json={"repo": bot_did, "collection": "app.bsky.feed.post", "record": record})
    r.raise_for_status()
    return r.json()

@retry_async()
async def post_reply(client, bot_did, text, root_uri, root_cid, parent_uri, parent_cid, facets=None, embed=None):
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat(), "reply": {"root": {"uri": root_uri, "cid": root_cid}, "parent": {"uri": parent_uri, "cid": parent_cid}}}
    if facets: record["facets"] = facets
    if embed: record["embed"] = embed
    r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json={"repo": bot_did, "collection": "app.bsky.feed.post", "record": record})
    r.raise_for_status()
    return r.json()

@retry_async()
async def post_like(client, bot_did, subject_uri, subject_cid):
    record = {"$type": "app.bsky.feed.like", "subject": {"$type": "com.atproto.repo.strongRef", "uri": subject_uri, "cid": subject_cid}, "createdAt": datetime.now(timezone.utc).isoformat()}
    r = await client.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", json={"repo": bot_did, "collection": "app.bsky.feed.like", "record": record})
    r.raise_for_status()
    return r.json()

@retry_async()
async def fetch_thread_chain(client, uri):
    r = await client.get("https://bsky.social/xrpc/app.bsky.feed.getPostThread", params={"uri": uri, "depth": 0, "parentHeight": 100})
    if r.status_code != 200: return None
    data, thread, chain = r.json(), r.json().get("thread", {}), []
    current = thread
    while current and isinstance(current, dict):
        p = current.get("post")
        if p: chain.append(p)
        current = current.get("parent")
    chain = list(reversed(chain))
    root_post = chain[0] if chain else thread.get("post", {})
    return {"root_uri": uri, "root_cid": root_post.get("cid", ""), "root_text": root_post.get("record", {}).get("text", ""), "cid": thread.get("post", {}).get("cid", ""), "chain": chain}

@retry_async()
async def fetch_notifications(client, limit=100, seen_at=None):
    params = {"limit": limit}
    if seen_at and seen_at not in ("{}", "null", "none"): params["seen_at"] = seen_at
    r = await client.get("https://bsky.social/xrpc/app.bsky.notification.listNotifications", params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("notifications", [])

def _extract_embed_text(embed):
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
    elif et in ("app.bsky.embed.record", "app.bsky.embed.recordWithMedia"):
        val = embed.get("record", {}).get("value", {})
        if val.get("text"): texts.append(val["text"])
        if et == "app.bsky.embed.recordWithMedia":
            med = embed.get("media", {})
            if med.get("$type") == "app.bsky.embed.images":
                for img in med.get("images", []):
                    if img.get("alt"): texts.append(img["alt"])
    return " ".join(texts)

async def _fetch_url_content(client, url):
    try:
        from trafilatura import extract as trafilatura_extract
        if httpx.URL(url).netloc not in config.ALLOWED_LINK_DOMAINS: return ""
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=config.REQUEST_TIMEOUT)
        if r.status_code == 200:
            txt = trafilatura_extract(r.text, include_tables=False, include_comments=False, output_format="txt")
            if txt: return txt
    except Exception: pass
    return ""

async def upload_digest_image(client, image_bytes: bytes, mime: str = "image/png", alt: str = ""):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        max_size = 976562
        if len(image_bytes) > max_size:
            img = img.convert("RGB")
            for q in [85, 75, 65]:
                buf = io.BytesIO(); img.save(buf, format="JPEG", quality=q, optimize=True)
                if buf.tell() <= max_size: image_bytes, mime = buf.getvalue(), "image/jpeg"; break
            else:
                img.thumbnail((1200, 800), Image.Resampling.LANCZOS)
                buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70, optimize=True)
                image_bytes, mime, w, h = buf.getvalue(), "image/jpeg", img.size
        r = await client.post("https://bsky.social/xrpc/com.atproto.repo.uploadBlob", content=image_bytes, headers={"Content-Type": mime, "Authorization": client.headers.get("Authorization", "")}, timeout=30)
        r.raise_for_status()
        blob = r.json().get("blob")
        if not blob: return None
        return {"$type": "app.bsky.embed.images", "images": [{"alt": alt or "Digest", "image": blob, "aspectRatio": {"width": w, "height": h}}]}
    except Exception as e:
        logger.warning(f"[bsky] Digest image upload failed: {e}")
        return None
