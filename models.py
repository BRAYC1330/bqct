from pydantic import BaseModel, field_validator, ConfigDict
from typing import Optional, Set, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import json
import re

class TaskType(str, Enum):
    digest_mini = "digest_mini"
    digest_full = "digest_full"
    digest_comment = "digest_comment"
    owner_command = "owner_command"

class DigestType(str, Enum):
    mini = "mini"
    full = "full"

class Task(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    type: TaskType
    uri: Optional[str] = None
    text: Optional[str] = None
    author_did: Optional[str] = None
    parent_uri: Optional[str] = None
    embed: Optional[Dict[str, Any]] = None

class BotState(BaseModel):
    model_config = ConfigDict(extra="ignore")
    seen_at: Optional[str] = None
    digest_uri: Optional[str] = None
    digest_time: Optional[str] = None
    digest_type: str = "mini"

    @field_validator("digest_type", mode="before")
    @classmethod
    def normalize_type(cls, v):
        if not v or str(v).strip().lower() in ("none", "null", "undefined", "{}", ""):
            return "mini"
        val = str(v).strip().lower()
        return val if val in ("mini", "full") else "mini"

    @field_validator("digest_time", "seen_at", mode="before")
    @classmethod
    def validate_iso_format(cls, v):
        return str(v).strip() if v else None

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def is_stale(self, hours: int = 2) -> bool:
        if not self.digest_time: return True
        try:
            dt_str = self.digest_time.replace("Z", "+00:00")
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            diff = (datetime.now(timezone.utc) - dt).total_seconds()
            return diff >= hours * 3600
        except Exception: return True

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
                return cls(query=q or fallback_query, time_range=t if t in ("day", "week", "month", "year") else "")
        except Exception: pass
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
        except Exception: return cls(value="")

class IntentClassification(BaseModel):
    is_substantive: bool = True

    @classmethod
    def from_raw(cls, raw: str) -> "IntentClassification":
        return cls(is_substantive="SUBSTANTIVE" in raw.upper())