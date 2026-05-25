import os
import json
import asyncio
import logging
import httpx
import time
import subprocess
from datetime import datetime, timezone
from typing import List
import config
import bsky
from models import Task, TaskType
from dispatcher import Dispatcher
from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

async def main() -> None:
    start_time = time.monotonic()
    logger.info("[BOT] === START ===")
    tasks_json = os.environ.get("TASKS_JSON", "[]")
    try:
        raw_tasks = json.loads(tasks_json)
        tasks: List[Task] = [Task(**t) for t in raw_tasks]
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.error(f"[BOT] Invalid TASKS_JSON: {e}")
        out_path = os.getenv("GITHUB_OUTPUT")
        if out_path:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write("new_digest_uri=\nbot_status=failure\n")
        return
    if not tasks:
        logger.warning("[BOT] Task list empty")
        out_path = os.getenv("GITHUB_OUTPUT")
        if out_path:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write("new_digest_uri=\nbot_status=success\n")
        return
    logger.info(f"[BOT] Loaded {len(tasks)} tasks")
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=5)
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        llm = None
        needs_llm = any(t.type in (TaskType.digest_mini, TaskType.digest_full, TaskType.digest_comment, TaskType.owner_command) for t in tasks)
        if needs_llm:
            import generator
            model_start = time.monotonic()
            try:
                llm = generator.get_model()
            except Exception as e:
                logger.error(f"[BOT] Model load failed: {e}")
                out_path = os.getenv("GITHUB_OUTPUT")
                if out_path:
                    with open(out_path, "a", encoding="utf-8") as f:
                        f.write("new_digest_uri=\nbot_status=failure\n")
                return
            logger.info(f"[BOT] Model loaded in {round(time.monotonic() - model_start, 2)}s")
        dispatcher = Dispatcher(client, llm)
        await dispatcher.run(tasks)
        logger.info(f"[BOT] Metrics: {dispatcher.metrics['success']} ok, {dispatcher.metrics['failed']} fail")
        out_path = os.getenv("GITHUB_OUTPUT")
        status = 'failure' if dispatcher.metrics['failed'] > 0 else 'success'
        if out_path:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(f"new_digest_uri={dispatcher.new_digest_uri}\n")
                f.write(f"bot_status={status}\n")
        if status == 'success':
            try:
                state = json.loads(os.environ.get("PREV_STATE_JSON", "{}"))
                sched_type = os.environ.get("SCHED_TYPE", "").strip()
                now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                if dispatcher.new_digest_uri:
                    state["digest_uri"] = dispatcher.new_digest_uri
                    state["digest_time"] = now_str
                if sched_type:
                    state["digest_type"] = sched_type
                final_json = json.dumps(state, ensure_ascii=False)
                repo = os.environ["GITHUB_REPOSITORY"]
                pat = os.environ["PAT"]
                subprocess.run(
                    ["gh", "secret", "set", "LAST_PROCESSED", "--body", final_json, "--repo", repo],
                    env={**os.environ, "GH_TOKEN": pat},
                    check=True
                )
                logger.info("[BOT] LAST_PROCESSED updated directly from runner")
            except Exception as e:
                logger.error(f"[BOT] Secret update failed: {e}")
    logger.info(f"[BOT] Total time: {round(time.monotonic() - start_time, 2)}s")
    logger.info("[BOT] === DONE ===")

if __name__ == "__main__":
    asyncio.run(main())