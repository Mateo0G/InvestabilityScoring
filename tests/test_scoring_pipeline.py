import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.extraction.normalize import Deck, Slide
from app.models.schemas import AnalysisResult, CategoryScore
from app.scoring.client import classify_slides, score_deck
from app.scoring.pipeline import compute_overall_score, run_scoring_pipeline
from app.scoring.rubric import CATEGORIES


def make_deck() -> Deck:
    return Deck(
        filename="deck.pdf",
        source_format="pdf",
        slides=[
            Slide(index=1, text_blocks=["Problem: nobody can benchmark their pitch deck."]),
            Slide(index=2, text_blocks=["Team: two ex-Stripe engineers."]),
        ],
    )


def make_valid_result() -> AnalysisResult:
    return AnalysisResult(
        category_scores=[
            CategoryScore(key=c.key, score=50, justification=f"Slide 1 mentions {c.label}.")
            for c in CATEGORIES
        ],
        strengths=["Clear problem statement on slide 1."],
        weaknesses=["No traction evidence anywhere in the deck."],
        action_items=[
            "Add traction metrics.",
            "Clarify the ask.",
            "Expand on go-to-market.",
        ],
    )


def make_usage(input_tokens=100, output_tokens=50):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def make_usage_info(input_tokens=100, output_tokens=50):
    from app.scoring.client import UsageInfo

    return UsageInfo(
        model="claude-sonnet-5",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        estimated_cost_usd=0.0,
    )


def test_compute_overall_score_uniform_50_is_50():
    result = make_valid_result()
    assert compute_overall_score(result) == 50.0


def test_compute_overall_score_weights_high_category_more():
    result = make_valid_result()
    # Bump the highest-weight category (team_execution, 15%) to 100
    for cs in result.category_scores:
        if cs.key == "team_execution":
            cs.score = 100
    score_bumped = compute_overall_score(result)

    result2 = make_valid_result()
    for cs in result2.category_scores:
        if cs.key == "fundraise_narrative_coherence":  # lowest weight, 5%
            cs.score = 100
    score_bumped_low_weight = compute_overall_score(result2)

    assert score_bumped > score_bumped_low_weight


@patch("app.scoring.client.get_client")
def test_score_deck_success(mock_get_client):
    fake_client = MagicMock()
    fake_response = SimpleNamespace(parsed_output=make_valid_result(), usage=make_usage())
    fake_client.messages.parse.return_value = fake_response
    mock_get_client.return_value = fake_client

    result, usage = score_deck(make_deck(), "deck.pdf")

    assert isinstance(result, AnalysisResult)
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
    fake_client.messages.parse.assert_called_once()
    call_kwargs = fake_client.messages.parse.call_args.kwargs
    assert call_kwargs["output_format"] is AnalysisResult
    assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


@patch("app.scoring.client.get_client")
def test_score_deck_retries_on_malformed_output(mock_get_client):
    fake_client = MagicMock()
    bad_response = SimpleNamespace(parsed_output=None, usage=make_usage())
    good_response = SimpleNamespace(parsed_output=make_valid_result(), usage=make_usage())
    fake_client.messages.parse.side_effect = [bad_response, good_response]
    mock_get_client.return_value = fake_client

    result, usage = score_deck(make_deck(), "deck.pdf")

    assert isinstance(result, AnalysisResult)
    assert fake_client.messages.parse.call_count == 2
    second_call_messages = fake_client.messages.parse.call_args.kwargs["messages"]
    assert len(second_call_messages) == 2  # original prompt + correction


@patch("app.scoring.client.get_client")
def test_score_deck_raises_after_exhausting_retries(mock_get_client):
    fake_client = MagicMock()
    bad_response = SimpleNamespace(parsed_output=None, usage=make_usage())
    fake_client.messages.parse.return_value = bad_response
    mock_get_client.return_value = fake_client

    with pytest.raises(ValueError):
        score_deck(make_deck(), "deck.pdf")


@patch("app.scoring.client.get_client")
def test_classify_slides_parses_json_response(mock_get_client):
    fake_client = MagicMock()
    payload = {"assignments": [{"slide_index": 1, "category": "problem_market_clarity"}]}
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        usage=make_usage(),
    )
    fake_client.messages.create.return_value = fake_response
    mock_get_client.return_value = fake_client

    mapping, usage = classify_slides(make_deck())

    assert mapping == {1: "problem_market_clarity"}
    assert usage.model


@patch("app.scoring.pipeline.score_deck")
@patch("app.scoring.pipeline.classify_slides")
def test_run_scoring_pipeline_aggregates_usage(mock_classify, mock_score):
    mock_classify.return_value = ({1: "problem_market_clarity"}, make_usage_info(10, 5))
    mock_score.return_value = (make_valid_result(), make_usage_info(200, 100))

    pipeline_result = run_scoring_pipeline(make_deck(), "deck.pdf")

    assert pipeline_result.overall_score == 50.0
    assert pipeline_result.total_input_tokens == 210
    assert pipeline_result.total_output_tokens == 105


@patch("app.scoring.pipeline.score_deck")
@patch("app.scoring.pipeline.classify_slides", side_effect=RuntimeError("classification down"))
def test_run_scoring_pipeline_tolerates_classification_failure(mock_classify, mock_score):
    mock_score.return_value = (make_valid_result(), make_usage_info(200, 100))

    pipeline_result = run_scoring_pipeline(make_deck(), "deck.pdf")

    assert pipeline_result.overall_score == 50.0
    assert pipeline_result.total_input_tokens == 200
