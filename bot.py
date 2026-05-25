import os
import json
import asyncio
import logging
import httpx
import time
from datetime import datetime, timezone
from typing import List
import config
import bsky
from models import Task, TaskType
from dispatcher import Dispatcher
from logging_config import setup_logging
from gh_io import write_outputs

setup_logging()
logger = logging.getLogger(__name__)

async def main() -> None:
    start_time = time.monotonic()
    tasks_json = os.environ.get("TASKS_JSON", "[]")
    try:
        tasks: List[Task] = [Task(**t) for t in json.loads(tasks_json)]
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.error(f"[BOT] Invalid TASKS_JSON: {e}")
        write_outputs(new_digest_uri="", bot_status="failure")
        return
    if not tasks:
        write_outputs(new_digest_uri="", bot_status="success")
        return
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=5)
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        await bsky.login_with_cache(client, config.BOT_HANDLE, config.BOT_PASSWORD)
        llm = None
        needs_llm = any(t.type in (TaskType.digest_mini, TaskType.digest_full, TaskType.digest_comment, TaskType.owner_command) for t in tasks)
        if needs_llm:
            import generator
            try:
                llm = generator.get_model()
            except Exception as e:
                logger.error(f"[BOT] Model load failed: {e}")
                write_outputs(new_digest_uri="", bot_status="failure")
                return
        dispatcher = Dispatcher(client, llm)
        await dispatcher.run(tasks)
        status = 'failure' if dispatcher.metrics['failed'] > 0 else 'success'
        write_outputs(new_digest_uri=dispatcher.new_digest_uri, bot_status=status)
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
                os.system(f'echo "{final_json}" | gh secret set LAST_PROCESSED --repo {os.environ["GITHUB_REPOSITORY"]}')
            except Exception as e:
                logger.error(f"[BOT] Secret update failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())