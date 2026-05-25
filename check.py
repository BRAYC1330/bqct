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
from gh_io import write_outputs

setup_logging()
logger = logging.getLogger(__name__)

def _did_from_uri(u):
    if not u:
        return None
    p = u.split("/")
    return p[2] if len(p) > 2 else None

async def run():
    last_processed_raw = os.getenv("LAST_PROCESSED", "{}").strip()
    try:
        state_data = json.loads(last_processed_raw) if last_processed_raw else {}
    except json.JSONDecodeError:
        state_data = {}
    state = BotState(**state_data)
    tasks, seen_uris = [], set()
    now_utc = datetime.now(timezone.utc)
    now_utc_str = now_utc.isoformat().replace("+00:00", "Z")
    owner_count = digest_comment_count = 0
    if not state.seen_at:
        state.seen_at = now_utc_str
    client = httpx.AsyncClient(timeout=30)
    try:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        notifs = await bsky.fetch_notifications(client, limit=100, seen_at=state.seen_at)
        for n in notifs:
            idx = n.get("indexedAt", "")
            if idx <= state.seen_at:
                continue
            uri, author_did, record = n.get("uri", ""), n.get("author", {}).get("did", ""), n.get("record", {})
            if uri in seen_uris:
                continue
            seen_uris.add(uri)
            if n.get("reason") not in ("reply", "mention"):
                continue
            text = (record.get("text") or "").strip()
            reply_data = record.get("reply", {}) if isinstance(record, dict) else {}
            parent_uri, root_uri = reply_data.get("parent", {}).get("uri", ""), reply_data.get("root", {}).get("uri", "")
            if author_did == config.OWNER_DID and n.get("reason") == "reply":
                if uri == root_uri and f"@{config.BOT_HANDLE.replace('@', '')}" not in text:
                    continue
                if state.digest_uri and root_uri == state.digest_uri and parent_uri != state.digest_uri:
                    continue
                if state.digest_uri and "/app.bsky.feed.post/" in root_uri:
                    if root_uri == state.digest_uri:
                        tasks.append(Task(type=TaskType.digest_comment, uri=uri, text=text, author_did=author_did, parent_uri=parent_uri, embed=record.get("embed")))
                        digest_comment_count += 1
                        continue
                    else:
                        continue
                if _did_from_uri(parent_uri) == config.BOT_DID:
                    tasks.append(Task(type=TaskType.owner_command, uri=uri, text=text, author_did=author_did, embed=record.get("embed")))
                    owner_count += 1
                    continue
                elif f"@{config.BOT_HANDLE.replace('@', '')}" in text:
                    tasks.append(Task(type=TaskType.owner_command, uri=uri, text=text, author_did=author_did, embed=record.get("embed")))
                    owner_count += 1
                    continue
                else:
                    continue
            if state.digest_uri and root_uri == state.digest_uri:
                if parent_uri and parent_uri != state.digest_uri and parent_uri.startswith(f"at://{config.BOT_DID}/"):
                    continue
                tasks.append(Task(type=TaskType.digest_comment, uri=uri, text=text, author_did=author_did, parent_uri=parent_uri, embed=record.get("embed")))
                digest_comment_count += 1
                continue
            if author_did == config.OWNER_DID:
                tasks.append(Task(type=TaskType.owner_command, uri=uri, text=text, author_did=author_did, embed=record.get("embed")))
                owner_count += 1
    finally:
        await client.aclose()
    scheduled_type = None
    manual = os.getenv("MANUAL_DIGEST_TYPE", "none").strip().lower()
    if manual in ("mini", "full"):
        scheduled_type = manual
    elif state.digest_time:
        try:
            last_dt = datetime.fromisoformat(state.digest_time.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if (now_utc - last_dt).total_seconds() >= config.DIGEST_THRESHOLD_HOURS * 3600:
                scheduled_type = "full" if state.digest_type == "mini" else "mini"
        except Exception:
            scheduled_type = "mini"
    else:
        scheduled_type = "mini"
    if scheduled_type:
        tasks.append(Task(type=TaskType[f"digest_{scheduled_type}"]))
    state.seen_at = now_utc_str
    has_tasks = len(tasks) > 0
    write_outputs(status='true' if has_tasks else 'false', tasks=json.dumps([t.model_dump() for t in tasks], ensure_ascii=False), state_json=state.model_dump_json(), scheduled_type=scheduled_type or "")
    if not has_tasks:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run())