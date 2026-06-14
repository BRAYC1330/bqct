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
                action = None
                if task.type in (TaskType.digest_mini, TaskType.digest_full):
                    import digest
                    action = await digest.prepare(self.llm, task.type, client=self.client)
                elif task.type == TaskType.digest_comment:
                    import community
                    action = await community.prepare(self.ctx, self.client, self.llm, task.model_dump())
                elif task.type == TaskType.owner_command:
                    import owner
                    action = await owner.prepare(self.client, self.llm, task.model_dump())
                else:
                    logger.warning(f"[DISPATCHER] Unknown task type: {task.type}")
                    self.metrics["failed"] += 1
                    continue
                if action and (not isinstance(action, list) or len(action) > 0):
                    if isinstance(action, list):
                        self.actions.extend(action)
                    else:
                        self.actions.append(action)
                    self.metrics["success"] += 1
                else:
                    logger.warning(f"[DISPATCHER] Task {task.type} returned empty result")
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
            elif act["type"] == "post_reply":
                await bsky.post_reply(self.client, **act["args"])
            elif act["type"] == "post_like":
                await bsky.post_like(self.client, **act["args"])
        except Exception as e:
            logger.error(f"[DISPATCHER] Commit failed for {act['type']}: {repr(e)}")
            self.metrics["failed"] += 1
