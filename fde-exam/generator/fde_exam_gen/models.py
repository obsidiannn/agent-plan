from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, field_validator


@dataclass
class TextBlock:
    page: int
    text: str
    kind: Literal["paragraph", "table", "subhead"]
    table_confidence: str | None = None
    y: float = 0.0


@dataclass
class Section:
    ref: str | None
    title: str
    page_start: int
    page_end: int
    blocks: list[TextBlock] = field(default_factory=list)


@dataclass
class Chapter:
    order_no: int
    title: str
    page_start: int
    page_end: int
    anchor: str
    sections: list[Section] = field(default_factory=list)
    blocks: list[TextBlock] = field(default_factory=list)


@dataclass
class Chunk:
    chapter_order: int
    chapter_title: str
    section_ref: str | None
    section_title: str | None
    order_no: int
    content: str
    page_start: int
    page_end: int
    table_confidence: str | None = None


@dataclass
class ParsedDocument:
    title: str
    page_count: int
    file_hash: str
    chapters: list[Chapter]
    images: list[dict] = field(default_factory=list)
    table_count: int = 0
    low_confidence_tables: int = 0


class OptionModel(BaseModel):
    key: Literal["A", "B", "C", "D", "E", "F"]
    content: str = Field(min_length=1, max_length=200)

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value):
        return str(value).strip().upper()


QuestionStyle = Literal[
    "SCENARIO",
    "TROUBLESHOOTING",
    "COMPARISON",
    "PROCESS",
    "CALCULATION",
    "JUDGMENT",
]


class GeneratedQuestion(BaseModel):
    type: Literal["SINGLE", "MULTIPLE"]
    style: QuestionStyle
    stem: str = Field(min_length=8, max_length=300)
    options: list[OptionModel] = Field(min_length=4, max_length=6)
    answer: list[str] = Field(min_length=1, max_length=4)
    explanation: str = Field(min_length=10, max_length=500)
    evidence_quote: str = Field(min_length=8, max_length=300)
    source_page: int = Field(ge=1)
    claim: str = Field(min_length=5, max_length=120)
    knowledge_point: str
    difficulty: Literal["EASY", "MEDIUM", "HARD"]

    @field_validator("type", "style", mode="before")
    @classmethod
    def normalize_upper(cls, value):
        return str(value).strip().upper()

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_answer(cls, value):
        if isinstance(value, list):
            return [str(item).strip().upper() for item in value]
        return value


class GeneratedQuestionBatch(BaseModel):
    questions: list[GeneratedQuestion]


class JudgeResult(BaseModel):
    grounded: int = Field(ge=1, le=5)
    unambiguous: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    distractor: int = Field(ge=1, le=5)
    difficulty_match: int = Field(ge=1, le=5)
    overall: float
    verdict: Literal["PASS", "FAIL", "REVISE"]
    issues: list[str] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def normalize_verdict(cls, value):
        return str(value).strip().upper()


class BlindResult(BaseModel):
    answer: list[str]
    confidence: float = Field(ge=0, le=1)
    reason: str = ""
