"""Pydantic schemas for the structured output Claude must return when scoring a deck.

Used both as the `output_format` passed to `client.messages.parse()` and as the
server-side validation layer the pipeline checks the parsed result against.
"""

from pydantic import BaseModel, Field, field_validator

from app.scoring.rubric import CATEGORIES

_VALID_KEYS = {c.key for c in CATEGORIES}


class CategoryScore(BaseModel):
    key: str = Field(description="One of the fixed rubric category keys.")
    score: int = Field(ge=0, le=100, description="Sub-score for this category, 0-100.")
    justification: str = Field(
        min_length=1,
        description="Justification grounded in specific slide content, not generic advice.",
    )

    @field_validator("key")
    @classmethod
    def key_must_be_known(cls, v: str) -> str:
        if v not in _VALID_KEYS:
            raise ValueError(f"Unknown rubric category key: {v!r}")
        return v


class AnalysisResult(BaseModel):
    category_scores: list[CategoryScore] = Field(
        description="One entry per rubric category - all categories must be present."
    )
    strengths: list[str] = Field(min_length=1)
    weaknesses: list[str] = Field(min_length=1)
    action_items: list[str] = Field(
        min_length=3,
        max_length=5,
        description="Prioritized, highest-impact fixes before pitching investors.",
    )

    @field_validator("category_scores")
    @classmethod
    def all_categories_present(cls, v: list[CategoryScore]) -> list[CategoryScore]:
        seen = {c.key for c in v}
        missing = _VALID_KEYS - seen
        if missing:
            raise ValueError(f"Missing scores for categories: {sorted(missing)}")
        return v
