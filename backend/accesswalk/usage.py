"""Provider-agnostic model-call usage log.

Every model call in the project -- SAM now, the Baseten/Fireworks agent loop on
Friday, Muse Voice Transcribe, the raw-video baseline -- appends one JSON line to
``data/out/usage.jsonl`` (git-ignored). This is the single audit trail for spend
and for "which model served this call" (open-weight eligibility).

Cache hits are logged too, with ``cache_hit=true`` and ``cost_usd=0.0``, so the
log is a complete record of what the pipeline asked for, not only what it paid
for.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_USAGE_LOG = REPO_ROOT / "data" / "out" / "usage.jsonl"


class UsageRecord(BaseModel):
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    provider: str  # "meta" | "baseten" | "fireworks" | "modal"
    model_requested: str
    model_served: str | None = None  # what the response says actually served it
    usage: dict = Field(default_factory=dict)  # raw usage dict from the response
    cache_hit: bool = False
    cost_usd: float | None = None
    video_sha256: str | None = None
    phrase: str | None = None
    extra: dict = Field(default_factory=dict)


def log_call(record: UsageRecord, path: str | Path = DEFAULT_USAGE_LOG) -> None:
    """Append one usage record as a JSON line."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def read_log(path: str | Path = DEFAULT_USAGE_LOG) -> list[UsageRecord]:
    """Read back all usage records (for eval/reporting; small file)."""
    p = Path(path)
    if not p.exists():
        return []
    return [UsageRecord.model_validate_json(line) for line in p.read_text().splitlines() if line.strip()]


def total_cost(path: str | Path = DEFAULT_USAGE_LOG) -> float:
    return sum(r.cost_usd or 0.0 for r in read_log(path))
