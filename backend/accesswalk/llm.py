"""Chat client for the verification agent: provider switch, response cache, usage log.

Providers (keys in .env, see .env.example):
  baseten    Muse Spark Open, open weights (primary; the open-weight bonus is judged on it)
  fireworks  the same open-weight model on a second host (automatic failover)
  meta       Muse Spark 1.3, closed. OFF unless the caller passes allow_closed=True; a
             run that used it says so in its provenance. Eval and demo runs never set it.

Every call is cached under ``data/cache/<video_sha>/llm/<key>.json`` where the key
hashes provider, model, messages, tool definitions and sampling params, so a re-run
is free and a changed tool schema never reuses an old answer. Every call, hit or
miss, is logged to ``usage.jsonl`` with the model the response says served it.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from openai import OpenAI

from . import usage
from .ingest import DEFAULT_OUT_ROOT

OPEN_PROVIDERS = ("baseten", "fireworks")
CLOSED_PROVIDER = "meta"
CLOSED_MODEL = "muse-spark-1.3"

# USD per 1M tokens (input, output). Fireworks is from its model page (Oct 28);
# Baseten is assumed equal until its invoice says otherwise.
PRICES = {
    "baseten": (1.25, 4.25),
    "fireworks": (1.25, 4.25),
    "meta": (1.25, 4.25),
}


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    api_key_env: str

    @property
    def is_open(self) -> bool:
        return self.name in OPEN_PROVIDERS


def providers_from_env() -> dict[str, Provider]:
    return {
        "baseten": Provider(
            "baseten", os.getenv("BASETEN_BASE_URL", "https://inference.baseten.co/v1"),
            os.getenv("BASETEN_MODEL", "meta-models/muse-spark-open-1026"), "BASETEN_API_KEY",
        ),
        "fireworks": Provider(
            "fireworks", os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"),
            os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/muse-spark-open"), "FIREWORKS_API_KEY",
        ),
        "meta": Provider(
            "meta", os.getenv("META_BASE_URL", "https://api.meta.ai/v1"), CLOSED_MODEL, "MODEL_API_KEY",
        ),
    }


def cache_key(provider: Provider, messages: list, tools: list | None, params: dict) -> str:
    blob = json.dumps(
        {"provider": provider.name, "model": provider.model, "messages": messages,
         "tools": tools or [], "params": params},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def cost_usd(provider: str, usage_dict: dict) -> float:
    pin, pout = PRICES.get(provider, (0.0, 0.0))
    return (usage_dict.get("prompt_tokens", 0) * pin + usage_dict.get("completion_tokens", 0) * pout) / 1e6


@dataclass
class ChatResult:
    message: dict  # assistant message as a plain dict (role, content, tool_calls)
    finish_reason: str | None
    usage: dict
    provider: str
    model_served: str | None
    cache_hit: bool
    cost_usd: float
    errors: list[str] = field(default_factory=list)  # failed providers before this one

    @property
    def used_closed_model(self) -> bool:
        return self.provider == CLOSED_PROVIDER


def _call(provider: Provider, messages: list, tools: list | None, params: dict, client=None) -> dict:
    client = client or OpenAI(api_key=os.environ[provider.api_key_env], base_url=provider.base_url)
    kwargs = dict(model=provider.model, messages=messages, **params)
    if tools:
        kwargs["tools"] = tools
    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    return {
        "message": choice.message.model_dump(exclude_none=True),
        "finish_reason": choice.finish_reason,
        "usage": resp.usage.model_dump() if resp.usage else {},
        "model_served": resp.model,
    }


def chat(
    messages: list,
    *,
    video_sha256: str,
    tools: list | None = None,
    params: dict | None = None,
    order: tuple[str, ...] = OPEN_PROVIDERS,
    allow_closed: bool = False,
    providers: dict[str, Provider] | None = None,
    out_root: str | Path = DEFAULT_OUT_ROOT,
    usage_log: str | Path = usage.DEFAULT_USAGE_LOG,
    call_fn=_call,
    tag: str = "agent",
) -> ChatResult:
    """One chat completion, trying providers in ``order`` (then the closed model only
    if ``allow_closed``). Raises if every provider fails."""
    params = params or {}
    providers = providers or providers_from_env()
    chain = list(order) + ([CLOSED_PROVIDER] if allow_closed else [])
    errors: list[str] = []
    for name in chain:
        p = providers[name]
        key = cache_key(p, messages, tools, params)
        cpath = Path(out_root) / video_sha256 / "llm" / f"{key}.json"
        if cpath.exists():
            data, hit, cost = json.loads(cpath.read_text(encoding="utf-8")), True, 0.0
        else:
            try:
                data = call_fn(p, messages, tools, params)
            except Exception as e:  # network, auth, 4xx/5xx: try the next host
                errors.append(f"{name}: {type(e).__name__}: {str(e)[:200]}")
                continue
            cost, hit = cost_usd(name, data["usage"]), False
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(
                json.dumps({**data, "provider": name, "model": p.model,
                            "created_at": datetime.now(UTC).isoformat()}, indent=2),
                encoding="utf-8",
            )
        usage.log_call(
            usage.UsageRecord(
                provider=name, model_requested=p.model, model_served=data.get("model_served"),
                usage=data["usage"], cache_hit=hit, cost_usd=cost, video_sha256=video_sha256,
                extra={"cache_key": key, "tag": tag, "failed_before": errors},
            ),
            path=usage_log,
        )
        return ChatResult(
            message=data["message"], finish_reason=data.get("finish_reason"), usage=data["usage"],
            provider=name, model_served=data.get("model_served"), cache_hit=hit, cost_usd=cost,
            errors=errors,
        )
    raise RuntimeError("all providers failed: " + " | ".join(errors))
