import logging

from app.extraction.normalize import Deck
from app.models.schemas import AnalysisResult
from app.scoring.client import UsageInfo, classify_slides, score_deck
from app.scoring.rubric import category_by_key

logger = logging.getLogger(__name__)


def compute_overall_score(result: AnalysisResult) -> float:
    """Deterministic, server-side weighted aggregate - never trust the model's
    own arithmetic for the headline score."""
    total = 0.0
    for cs in result.category_scores:
        weight = category_by_key(cs.key).weight
        total += cs.score * (weight / 100)
    return round(total, 1)


class PipelineResult:
    def __init__(
        self,
        analysis_result: AnalysisResult,
        overall_score: float,
        total_input_tokens: int,
        total_output_tokens: int,
        total_cost_usd: float,
    ):
        self.analysis_result = analysis_result
        self.overall_score = overall_score
        self.total_input_tokens = total_input_tokens
        self.total_output_tokens = total_output_tokens
        self.total_cost_usd = total_cost_usd


def run_scoring_pipeline(deck: Deck, filename: str) -> PipelineResult:
    usages: list[UsageInfo] = []

    try:
        _slide_categories, classify_usage = classify_slides(deck)
        usages.append(classify_usage)
    except Exception:
        logger.warning("Slide classification step failed; continuing without it.", exc_info=True)

    result, scoring_usage = score_deck(deck, filename)
    usages.append(scoring_usage)

    overall_score = compute_overall_score(result)

    for u in usages:
        logger.info(
            "Claude usage: model=%s input_tokens=%d output_tokens=%d cost_usd=%.4f",
            u.model,
            u.input_tokens,
            u.output_tokens,
            u.estimated_cost_usd,
        )

    return PipelineResult(
        analysis_result=result,
        overall_score=overall_score,
        total_input_tokens=sum(u.input_tokens for u in usages),
        total_output_tokens=sum(u.output_tokens for u in usages),
        total_cost_usd=sum(u.estimated_cost_usd for u in usages),
    )
