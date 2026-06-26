from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set
from pydantic import BaseModel, ConfigDict

class TaskType(str, Enum):
    digest_mini = "digest_mini"
    digest_full = "digest_full"
    digest_comment = "digest_comment"
    owner_command = "owner_command"
    scout = "scout"

class DigestType(str, Enum):
    mini = "mini"
    full = "full"

class BotState(BaseModel):
    model_config = ConfigDict(extra="ignore")
    seen_at: str = ""
    digest_uri: str = ""
    digest_time: str = ""
    digest_type: str = "mini"
    scout_greeted: List[str] = []

    def should_run_digest(self, hours: float) -> bool:
        if not self.digest_time: return True
        try:
            from datetime import datetime, timezone
            now_utc = datetime.now(timezone.utc)
            last_dt = datetime.fromisoformat(self.digest_time.replace("Z", "+00:00"))
            if last_dt.tzinfo is None: last_dt = last_dt.replace(tzinfo=timezone.utc)
            diff = (now_utc - last_dt).total_seconds()
            return diff >= hours * 3600
        except Exception:
            return True

    def next_digest_type(self) -> DigestType:
        return DigestType.full if self.digest_type == "mini" else DigestType.mini

class Task(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: TaskType
    uri: str = ""
    text: str = ""
    author_did: str = ""
    parent_uri: str = ""
    embed: dict | None = None

@dataclass
class RunContext:
    max_likes: int = 10
    likes_count: int = 0
    liked_uris: Set[str] = field(default_factory=set)

    def like(self, uri: str) -> bool:
        if uri in self.liked_uris: return False
        self.liked_uris.add(uri)
        return True

    def try_casual_like(self, uri: str) -> bool:
        if uri in self.liked_uris: return False
        if self.likes_count < self.max_likes:
            self.liked_uris.add(uri)
            self.likes_count += 1
            return True
        return False