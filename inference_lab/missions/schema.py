"""Mission definition schema. Missions are data (YAML), validated by these models.

See docs/MISSION_SCHEMA.md for the authoring guide.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

LANGS = ("en", "zh-TW")


class Loc(BaseModel):
    """A localized string. Both languages are mandatory."""

    model_config = {"extra": "forbid", "populate_by_name": True}
    en: str = Field(min_length=1)
    zh_TW: str = Field(min_length=1, alias="zh-TW")

    def get(self, lang: str) -> str:
        return self.zh_TW if lang == "zh-TW" else self.en


Op = Literal["eq", "ne", "gt", "gte", "lt", "lte", "exists", "truthy", "in", "len_gte", "contains"]


class Check(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    description: Loc
    path: str = Field(pattern=r"^(run|result)(\.[A-Za-z0-9_\-]+)*$")
    op: Op
    value: Any = None


class SourceRef(BaseModel):
    model_config = {"extra": "forbid"}
    file: str
    symbol: str | None = None


class StepAction(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    params: dict[str, Any] = Field(default_factory=dict)
    editable: list[str] = Field(default_factory=list)


class Quiz(BaseModel):
    model_config = {"extra": "forbid"}
    question: Loc
    options: list[Loc] = Field(min_length=2)
    answer: int
    explanation: Loc

    @model_validator(mode="after")
    def _answer_in_range(self) -> "Quiz":
        if not 0 <= self.answer < len(self.options):
            raise ValueError("quiz answer index out of range")
        return self


class Step(BaseModel):
    model_config = {"extra": "forbid"}
    id: str
    title: Loc
    what: Loc
    why: Loc
    concept: str | None = None
    action: StepAction | None = None
    expected: Loc
    checks: list[Check] = Field(default_factory=list)
    failure: Loc
    hints: list[Loc] = Field(default_factory=list, description="progressive: vague first, specific last")
    sources: list[SourceRef] = Field(default_factory=list)
    alternatives: Loc | None = None
    reproduce: Loc | None = None
    optional: bool = False
    requires_capabilities: list[str] = Field(default_factory=list)
    quiz: Quiz | None = None

    @model_validator(mode="after")
    def _checks_need_action(self) -> "Step":
        if self.action is None and self.quiz is None:
            raise ValueError(f"step {self.id}: needs an action or a quiz")
        if self.action is not None and not self.checks:
            raise ValueError(f"step {self.id}: an action step needs at least one validation check")
        return self


class Challenge(BaseModel):
    model_config = {"extra": "forbid"}
    prompt: Loc
    action: StepAction
    checks: list[Check] = Field(min_length=1)


class Mission(BaseModel):
    model_config = {"extra": "forbid"}
    id: str = Field(pattern=r"^m0[1-9]-[a-z0-9-]+$")
    number: int
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: Loc
    tagline: Loc
    objectives: list[Loc] = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(min_length=1)
    challenge: Challenge | None = None
    optional_experiments: list[Loc] = Field(default_factory=list)
    completion_evidence: Loc
