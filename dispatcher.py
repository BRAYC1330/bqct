import logging, time
from typing import List, Optional, Dict, Any
import httpx
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
        self._handlers = {
            TaskType.digest_mini: self._run_digest,
            TaskType.digest_full: self._run_digest,
            TaskType.digest_comment: self._run_community,
            TaskType.owner_command: self._run_owner
        }

    async def _run_digest(self, task: Task) -> Optional[Dict[str, Any]]:
        import digest
        return await digest.prepare(self.llm, task.type, client=self.client)

    async def _run_community(self, task: Task) -> Optional[List[Dict[str, Any]]]:
        import community
        return await community.prepare(self.ctx, self.client, self.llm, task.model_dump())

    async def _run_owner(self, task: Task) -> Optional[List[Dict[str, Any]]]:
        import owner
        return await owner.prepare(self.client, self.llm, task.model_dump())

    async def run(self, tasks: List[Task]) -> None:
        self.metrics["total_tasks"] = len(tasks)
        exec_start = time.monotonic()
        for idx, task in enumerate(tasks):
            logger.info(f"[DISPATCHER] Preparing task #{idx}: {task.type}")
            try:
                handler = self._handlers.get(task.type)
                if not handler:
                    logger.warning(f"[DISPATCHER] Unknown task type: {task.type}")
                    self.metrics["failed"] += 1
                    continue
                res = await handler(task)
                if res is not None:
                    self.actions.extend(res if isinstance(res, list) else [res])
                    self.metrics["success"] += 1
                else:
                    self.metrics["failed"] += 1
            except Exception as e:
                logger.error(f"[DISPATCHER] Task {task.type} failed: {repr(e)}")
                self.metrics["failed"] += 1
        self.metrics["execution_time"] = round(time.monotonic() - exec_start, 2)

        if self.actions:
            logger.info(f"[DISPATCHER] Committing {len(self.actions)} actions...")
            for act in self.actions: await self._execute_action(act)
        if self.metrics["failed"] > 0:
            logger.warning(f"[DISPATCHER] {self.metrics['failed']} tasks failed")

    async def _execute_action(self, act: Dict[str, Any]) -> None:
        try:
            if act["type"] == "post_root":
                res = await bsky.post_root(self.client, **act["args"])
                if act.get("track_uri"): self.new_digest_uri = res.get("uri", "")
            elif act["type"] == "post_reply":
                await bsky.post_reply(self.client, **act["args"])
            elif act["type"] == "post_like":
                await bsky.post_like(self.client, **act["args"])
        except Exception as e:
            logger.error(f"[DISPATCHER] Commit failed for {act['type']}: {repr(e)}")
            self.metrics["failed"] += 1
