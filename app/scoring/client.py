import json
import logging
from dataclasses import dataclass
from functools import lru_cache

import anthropic
import pydantic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.extraction.normalize import Deck
from app.models.schemas import AnalysisResult
from app.scoring.pricing import estimate_cost_usd
from app.scoring.prompts import SCORING_SYSTEM_PROMPT, build_scoring_user_prompt
from app.scoring.rubric import CATEGORIES

logger = logging.getLogger(__name__)

_MAX_VALIDATION_RETRIES = 2

_RETRYABLE_API_ERRORS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)


@dataclass
class UsageInfo:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    estimated_cost_usd: float


@lru_cache
def get_client() -> anthropic.Anthropic:
    settings = get_settings()
    return anthropic.Anthropic(api_key=settings.anthropic_api_key or None)


def _usage_from_response(model: str, response) -> UsageInfo:
    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return UsageInfo(
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        estimated_cost_usd=estimate_cost_usd(
            model, usage.input_tokens, usage.output_tokens, cache_read, cache_creation
        ),
    )


@retry(
    retry=retry_if_exception_type(_RETRYABLE_API_ERRORS),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    reraise=True,
)
def classify_slides(deck: Deck) -> tuple[dict[int, str], UsageInfo]:
    """Haiku pre-processing step: assign each non-empty slide to its most relevant
    rubric category (or 'unclear'). Used to ground the Sonnet scoring prompt and
    keep the expensive model call focused on judgment, not classification.
    """
    settings = get_settings()
    client = get_client()

    valid_keys = [c.key for c in CATEGORIES] + ["unclear"]
    slide_list = "\n".join(
        f"Slide {s.index}: {s.text[:300]}" for s in deck.slides if not s.is_empty
    )

    schema = {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "slide_index": {"type": "integer"},
                        "category": {"type": "string", "enum": valid_keys},
                    },
                    "required": ["slide_index", "category"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["assignments"],
        "additionalProperties": False,
    }

    response = client.messages.create(
        model=settings.claude_extraction_model,
        max_tokens=2048,
        system="Classify each pitch deck slide into the single rubric category it most "
        "relates to. Use 'unclear' if a slide doesn't clearly map to any category "
        "(e.g. a title slide or table of contents).",
        messages=[{"role": "user", "content": slide_list}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    mapping = {a["slide_index"]: a["category"] for a in data["assignments"]}
    return mapping, _usage_from_response(settings.claude_extraction_model, response)


@retry(
    retry=retry_if_exception_type(_RETRYABLE_API_ERRORS),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    reraise=True,
)
def _call_sonnet_for_scoring(model: str, user_prompt: str, correction: str | None):
    client = get_client()
    messages = [{"role": "user", "content": user_prompt}]
    if correction:
        messages.append({"role": "user", "content": correction})

    return client.messages.parse(
        model=model,
        max_tokens=8192,
        system=[
            {
                "type": "text",
                "text": SCORING_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
        output_format=AnalysisResult,
    )


def score_deck(deck: Deck, filename: str) -> tuple[AnalysisResult, UsageInfo]:
    """Sonnet scoring call against the deck text, validated against AnalysisResult.

    Retries with a corrective follow-up message if the model's output fails
    pydantic validation (e.g. missing a rubric category) - separate from the
    transient-API-error retries handled by _call_sonnet_for_scoring.
    """
    settings = get_settings()
    model = settings.claude_scoring_model
    user_prompt = build_scoring_user_prompt(deck.to_prompt_text(), filename)

    correction: str | None = None
    last_error: Exception | None = None

    for attempt in range(_MAX_VALIDATION_RETRIES + 1):
        response = _call_sonnet_for_scoring(model, user_prompt, correction)
        try:
            result = response.parsed_output
            if result is None:
                raise ValueError("Model response did not include parsed structured output.")
            return result, _usage_from_response(model, response)
        except (pydantic.ValidationError, ValueError) as e:
            last_error = e
            logger.warning("Scoring output failed validation (attempt %d): %s", attempt + 1, e)
            correction = (
                "Your previous response did not match the required schema "
                f"({e}). Return a corrected response including every rubric category."
            )

    raise last_error
