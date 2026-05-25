import os, json, asyncio, logging, httpx, time
from datetime import datetime, timezone
from typing import List
import config, bsky
from models import Task, TaskType
from dispatcher import Dispatcher
from logging_config import setup_logging
from gh_io import write_outputs
setup_logging()
logger = logging.getLogger(__name__)

async def main() -> None:
    start_time = time.monotonic()
    logger.info("[BOT] === START ===")
    tasks_json = os.environ.get("TASKS_JSON", "[]")
    try:
        tasks: List[Task] = [Task(**t) for t in json.loads(tasks_json)]
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.error(f"[BOT] Invalid TASKS_JSON: {e}")
        write_outputs(new_digest_uri="", bot_status="failure")
        return

    if not tasks:
        logger.warning("[BOT] Task list empty")
        write_outputs(new_digest_uri="", bot_status="success")
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
            try: llm = generator.get_model()
            except Exception as e:
                logger.error(f"[BOT] Model load failed: {e}")
                write_outputs(new_digest_uri="", bot_status="failure")
                return
            logger.info(f"[BOT] Model loaded in {round(time.monotonic() - model_start, 2)}s")

        dispatcher = Dispatcher(client, llm)
        await dispatcher.run(tasks)
        logger.info(f"[BOT] Metrics: {dispatcher.metrics['success']} ok, {dispatcher.metrics['failed']} fail")

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
                if sched_type: state["digest_type"] = sched_type
                final_json = json.dumps(state, ensure_ascii=False)
                os.system(f'echo "{final_json}" | gh secret set LAST_PROCESSED --repo {os.environ["GITHUB_REPOSITORY"]}')
                logger.info("[BOT] LAST_PROCESSED updated via gh cli")
            except Exception as e:
                logger.error(f"[BOT] Secret update failed: {e}")

    logger.info(f"[BOT] Total time: {round(time.monotonic() - start_time, 2)}s")
    logger.info("[BOT] === DONE ===")

if __name__ == "__main__": asyncio.run(main())
