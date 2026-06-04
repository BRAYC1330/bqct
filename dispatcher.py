import logging
import time
from typing import List, Optional, Dict, Any
import httpx
import config
from models import Task, TaskType, RunContext
import bsky
logger = logging.getLogger(__name__)
class Dispatcher:
    def __init__(self, client: httpx.AsyncClient, llm: Optional[object] = None):
        self.client = client
        self.llm = llm
        self.ctx = RunContext()
        self.metrics = {"total_tasks": 0, "success": 0, "failed": 0, "execution_time": 0.0}
        self.actions: List[Dict[str, Any]] = []
        self.new_digest_uri = ""
    async def run(self, tasks: List[Task]) -> None:
        self.metrics["total_tasks"] = len(tasks)
        exec_start = time.monotonic()
        for idx, task in enumerate(tasks):
            logger.info(f"[DISPATCHER] Preparing task #{idx}: {task.type}")
            try:
                if task.type in (TaskType.digest_mini, TaskType.digest_full):
                    import digest
                    action = await digest.prepare(self.llm, task.type, client=self.client)
                    if action is not None:
                        self.actions.append(action)
                        self.metrics["success"] += 1
                    else:
                        self.metrics["failed"] += 1
                elif task.type == TaskType.digest_comment:
                    import community
                    action = await community.prepare(self.ctx, self.client, self.llm, task.model_dump())
                    if action is not None:
                        if isinstance(action, list):
                            self.actions.extend(action)
                        else:
                            self.actions.append(action)
                        self.metrics["success"] += 1
                    else:
                        self.metrics["failed"] += 1
                elif task.type == TaskType.owner_command:
                    import owner
                    action = await owner.prepare(self.client, self.llm, task.model_dump())
                    if action is not None:
                        if isinstance(action, list):
                            self.actions.extend(action)
                        else:
                            self.actions.append(action)
                        self.metrics["success"] += 1
                    else:
                        self.metrics["failed"] += 1
                else:
                    logger.warning(f"[DISPATCHER] Unknown task type: {task.type}")
                    self.metrics["failed"] += 1
            except Exception as e:
                logger.error(f"[DISPATCHER] Task {task.type} preparation failed: {repr(e)}")
                self.metrics["failed"] += 1
        self.metrics["execution_time"] = round(time.monotonic() - exec_start, 2)
        if self.metrics["failed"] == 0 and self.actions:
            logger.info(f"[DISPATCHER] Committing {len(self.actions)} actions...")
            for act in self.actions:
                await self._execute_action(act)
            if self.metrics["failed"] > 0:
                logger.warning("[DISPATCHER] Commit partially failed")
        elif self.metrics["failed"] > 0:
            logger.warning(f"[DISPATCHER] Aborting commit due to {self.metrics['failed']} failed tasks")
            self.actions.clear()
    async def _execute_action(self, act: Dict[str, Any]) -> None:
        try:
            if act["type"] == "post_root":
                res = await bsky.post_root(self.client, **act["args"])
                if act.get("track_uri"):
                    self.new_digest_uri = res.get("uri", "")
                await self._mirror_to_x(act)
            elif act["type"] == "post_reply":
                await bsky.post_reply(self.client, **act["args"])
            elif act["type"] == "post_like":
                await bsky.post_like(self.client, **act["args"])
        except Exception as e:
            logger.error(f"[DISPATCHER] Commit failed for {act['type']}: {repr(e)}")
            self.metrics["failed"] += 1
    async def _mirror_to_x(self, act: Dict[str, Any]) -> None:
        logger.info(f"[x] === X MIRROR START ===")
        logger.info(f"[x] X_POSTING_ENABLED: {config.X_POSTING_ENABLED}")
        if not config.X_POSTING_ENABLED:
            logger.info("[x] X posting disabled, skipping")
            logger.info(f"[x] === X MIRROR END (disabled) ===")
            return
        logger.info(f"[x] X_USERNAME set: {bool(config.X_USERNAME)}")
        logger.info(f"[x] X_COOKIES set: {bool(config.X_COOKIES)}")
        try:
            import x_client
            text = act["args"].get("text", "")
            image_bytes = act.get("x_image_bytes")
            logger.info(f"[x] Text length: {len(text)} chars")
            logger.info(f"[x] Has image: {image_bytes is not None} ({len(image_bytes) if image_bytes else 0} bytes)")
            if len(text) > 280:
                original_len = len(text)
                text = text[:277].rstrip() + "..."
                logger.info(f"[x] Text truncated: {original_len} → {len(text)} (X limit: 280)")
            tweet_id = await x_client.post_to_x(text, image_bytes)
            if tweet_id:
                logger.info(f"[x] ✅ Mirrored to X: tweet_id={tweet_id}")
            else:
                logger.warning("[x] ⚠️ post_to_x returned None (no tweet_id)")
        except Exception as e:
            logger.warning(f"[x] ⚠️ X mirror failed (non-critical): {type(e).__name__}: {repr(e)}")
        logger.info(f"[x] === X MIRROR END ===")
