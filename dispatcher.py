import logging
import time
import asyncio
from typing import List, Optional, Dict, Any
import httpx
import config
from models import Task, TaskType, RunContext
import bsky
import digest
import community
import owner

logger = logging.getLogger(__name__)

class Dispatcher:
    def __init__(self, client: httpx.AsyncClient, llm: Optional[object] = None):
        self.client = client
        self.llm = llm
        self.ctx = RunContext()
        self.metrics = {"total_tasks": 0, "success": 0, "failed": 0, "execution_time": 0.0}
        self.actions: List[Dict[str, Any]] = []
        self.new_digest_uri = ""

    async def _prepare_single_task(self, task: Task):
        try:
            if task.type in (TaskType.digest_mini, TaskType.digest_full):
                return await digest.prepare(self.llm, task.type, client=self.client)
            elif task.type == TaskType.digest_comment:
                return await community.prepare(self.ctx, self.client, self.llm, task)
            elif task.type == TaskType.owner_command:
                return await owner.prepare(self.client, self.llm, task)
            else:
                logger.warning(f"[DISPATCHER] Unknown task type: {task.type}")
                return None
        except Exception as e:
            logger.error(f"[DISPATCHER] Task {task.type} preparation failed: {repr(e)}")
            return None

    async def run(self, tasks: List[Task]) -> None:
        self.metrics["total_tasks"] = len(tasks)
        exec_start = time.monotonic()
        
        results = await asyncio.gather(*[self._prepare_single_task(t) for t in tasks])
        
        for res in results:
            if isinstance(res, list) and len(res) > 0:
                self.actions.extend(res)
                self.metrics["success"] += 1
            elif isinstance(res, dict):
                self.actions.append(res)
                self.metrics["success"] += 1
            else:
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
