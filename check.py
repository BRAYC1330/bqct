import os
import sys
import json
import asyncio
import logging
import httpx
from datetime import datetime, timezone
import config
import bsky
from models import BotState, Task, TaskType
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def _did_from_uri(u):
    if not u: return None
    p = u.split("/")
    return p[2] if len(p) > 2 else None

async def run():
    last_processed_raw = os.getenv("LAST_PROCESSED", "{}").strip()
    try:
        state_data = json.loads(last_processed_raw) if last_processed_raw else {}
    except json.JSONDecodeError:
        state_data = {}
    state = BotState(**state_data)
    logger.info(f"[checker] LAST_PROCESSED state: {state.model_dump_json()}")

    tasks = []
    seen_uris = set()
    now_utc = datetime.now(timezone.utc)
    now_utc_str = now_utc.isoformat().replace("+00:00", "Z")
    owner_count = 0
    digest_comment_count = 0

    if not state.seen_at:
        state.seen_at = now_utc_str

    client = httpx.AsyncClient(timeout=30)
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        notifs = await bsky.fetch_notifications(client, limit=100, seen_at=state.seen_at)
        for n in notifs:
            idx = n.get("indexedAt", "")
            if idx <= state.seen_at: continue
            uri = n.get("uri", "")
            if uri in seen_uris: continue
            seen_uris.add(uri)
            reason = n.get("reason", "")
            if reason not in ("reply", "mention"): continue
            author_did = n.get("author", {}).get("did", "")
            record = n.get("record", {})
            text = (record.get("text") or "").strip()
            embed = record.get("embed")
            reply_data = record.get("reply", {}) if isinstance(record, dict) else {}
            parent_uri = reply_data.get("parent", {}).get("uri", "")
            root_uri = reply_data.get("root", {}).get("uri", "")

            if author_did == config.OWNER_DID and reason == "reply":
                if uri == root_uri and f"@{config.BOT_HANDLE.replace('@', '')}" not in text:
                    logger.info(f"[checker] Skipping owner branch-start reply (uri==root_uri, no @mention): {uri}")
                    continue

                if state.digest_uri and root_uri == state.digest_uri and parent_uri != state.digest_uri:
                    logger.info(f"[checker] Skipping nested owner reply in digest thread: root={state.digest_uri}, parent={parent_uri}")
                    continue

                if state.digest_uri and "/app.bsky.feed.post/" in root_uri:
                    if root_uri == state.digest_uri:
                        tasks.append(Task(type=TaskType.digest_comment, uri=uri, text=text, author_did=author_did, parent_uri=parent_uri, embed=embed))
                        digest_comment_count += 1
                        logger.info(f"[debug] queued digest_comment (owner in CURRENT digest) | uri={uri}")
                    else:
                        logger.info(f"[checker] Skipping owner reply to OLD digest thread: root={root_uri}, current={state.digest_uri}")
                    continue

                parent_author_did = _did_from_uri(parent_uri)
                if parent_author_did == config.BOT_DID:
                    tasks.append(Task(type=TaskType.owner_command, uri=uri, text=text, author_did=author_did, embed=embed))
                    owner_count += 1
                    logger.info(f"[debug] queued owner_command (owner->bot outside digest) | uri={uri}")
                    continue
                elif f"@{config.BOT_HANDLE.replace('@', '')}" in text:
                    tasks.append(Task(type=TaskType.owner_command, uri=uri, text=text, author_did=author_did, embed=embed))
                    owner_count += 1
                    continue
                else:
                    continue

            if state.digest_uri and root_uri == state.digest_uri:
                if parent_uri and parent_uri != state.digest_uri and parent_uri.startswith(f"at://{config.BOT_DID}/"):
                    continue
                tasks.append(Task(type=TaskType.digest_comment, uri=uri, text=text, author_did=author_did, parent_uri=parent_uri, embed=embed))
                digest_comment_count += 1
                continue

            if author_did == config.OWNER_DID:
                tasks.append(Task(type=TaskType.owner_command, uri=uri, text=text, author_did=author_did, embed=embed))
                owner_count += 1
    finally:
        await client.aclose()

    scheduled_type = None
    manual_digest_type = os.getenv("MANUAL_DIGEST_TYPE", "none").strip().lower()
    if manual_digest_type in ("mini", "full"):
        scheduled_type = manual_digest_type
        logger.info(f"[MANUAL] Digest override: {scheduled_type}")
    elif state.digest_time:
        try:
            last_dt = datetime.fromisoformat(state.digest_time.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            diff_sec = (now_utc - last_dt).total_seconds()
            diff_hours = diff_sec / 3600
            logger.info(f"[TIMER] Last digest {diff_hours:.2f}h ago (threshold: {config.DIGEST_THRESHOLD_HOURS}h)")
            if diff_sec >= config.DIGEST_THRESHOLD_HOURS * 3600:
                scheduled_type = "full" if state.digest_type == "mini" else "mini"
        except Exception as e:
            logger.warning(f"[TIMER] Time parse error: {e}, fallback mini")
            scheduled_type = "mini"
    else:
        scheduled_type = "mini"

    if scheduled_type:
        tasks.append(Task(type=TaskType[f"digest_{scheduled_type}"]))
        logger.info(f"[TIMER] Digest scheduled: {scheduled_type}")

    state.seen_at = now_utc_str
    tasks_json = json.dumps([t.model_dump() for t in tasks], ensure_ascii=False)
    out_path = os.getenv("GITHUB_OUTPUT")
    has_tasks = len(tasks) > 0
    if out_path:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"status={'true' if has_tasks else 'false'}\n")
            f.write(f"tasks={tasks_json}\n")
            f.write(f"state_json={state.model_dump_json()}\n")
            f.write(f"scheduled_type={scheduled_type or ''}\n")
    logger.info(f"[checker] Tasks: {len(tasks)} (Owner: {owner_count}, Community: {digest_comment_count}, Digest: {scheduled_type or 'none'})")
    if not has_tasks:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run())
