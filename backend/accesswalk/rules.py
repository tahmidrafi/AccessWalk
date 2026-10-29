"""Load and validate ``rules.yaml`` (the 8 MVP checks). See the YAML header."""
from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Literal, get_args

import yaml
from pydantic import BaseModel, Field, model_validator

from .schemas import CheckId, Severity

RULES_PATH = Path(__file__).with_name("rules.yaml")


class Rule(BaseModel):
    title: str
    question: str
    evidence_phrases: list[str] = Field(min_length=1)
    judged_from: Literal["track", "keyframe"]
    verify_manually: Literal["always", "never"]
    severity: dict[Severity, str]
    reference: str
    pitfalls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _all_bins(self) -> Rule:
        if set(self.severity) != set(get_args(Severity)):
            raise ValueError("severity must define low, medium and high")
        return self


class Rules(BaseModel):
    checks: dict[CheckId, Rule]

    @model_validator(mode="after")
    def _all_checks(self) -> Rules:
        missing = set(get_args(CheckId)) - set(self.checks)
        if missing:
            raise ValueError(f"rules.yaml is missing checks: {sorted(missing)}")
        return self


@cache
def load_rules(path: Path = RULES_PATH) -> Rules:
    return Rules.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
