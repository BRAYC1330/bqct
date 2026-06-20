from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set
from pydantic import BaseModel, ConfigDict


class TaskType(str, Enum):
    digest_mini = "digest_mini"
    digest_full = "digest_full"
    digest_comment = "digest_comment"
    owner_command = "owner_command"


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
        if not self.digest_time:
            return True
        try:
            from datetime import datetime, timezone
            now_utc = datetime.now(timezone.utc)
            last_dt = datetime.fromisoformat(self.digest_time.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            diff = (now_utc - last_dt).total_seconds()
            return diff >= hours * 3600
        except Exception:
            return True

    def next_digest_type(self) -> DigestType:
        return DigestType.full if self.digest_type == "mini" else DigestType.mini


@dataclass
class RunContext:
    max_likes: int = 10
    likes_count: int = 0
    liked_uris: Set[str] = field(default_factory=set)

    def like(self, uri: str) -> bool:
        if uri in self.liked_uris:
            return False
        self.liked_uris.add(uri)
        return True

    def try_casual_like(self, uri: str) -> bool:
        if uri in self.liked_uris:
            return False
        if self.likes_count < self.max_likes:
            self.liked_uris.add(uri)
            self.likes_count += 1
            return True
        return False


class SearchIntent(BaseModel):
    query: str
    time_range: str = ""

    @classmethod
    def from_raw(cls, raw: str, fallback_query: str) -> "SearchIntent":
        try:
            if "| TIME:" in raw:
                q_part, t_part = raw.split("| TIME:", 1)
                q = q_part.replace("QUERY:", "").strip().strip('"')
                t = t_part.strip().lower()
                return cls(
                    query=q or fallback_query,
                    time_range=t if t in ("day", "week", "month", "year") else ""
                )
        except Exception:
            pass
        return cls(query=fallback_query)


class Keyword(BaseModel):
    value: str = ""

    @classmethod
    def from_raw(cls, raw: str) -> "Keyword":
        try:
            clean = raw.strip()
            if "KEYWORD:" in clean.upper():
                clean = clean.split("KEYWORD:")[-1].strip()
            val = re.sub(r'[^\w\s]', '', clean).split()[0] if clean else ""
            return cls(value=val)
        except Exception:
            return cls(value="")


class IntentClassification(BaseModel):
    is_substantive: bool = True

    @classmethod
    def from_raw(cls, raw: str) -> "IntentClassification":
        return cls(is_substantive="SUBSTANTIVE" in raw.upper())
