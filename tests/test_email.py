from unittest.mock import MagicMock, patch

from app.models.db import Analysis
from app.notifications.email import build_result_email_html, send_result_email


def make_analysis() -> Analysis:
    return Analysis(
        id=1,
        session_id="s1",
        filename="deck.pdf",
        source_format="pdf",
        slide_count=2,
        status="complete",
        overall_score=72.5,
        category_scores={
            "team_execution": {"score": 80, "justification": "Slide 3 shows a strong team."},
            "traction_validation": {"score": 60, "justification": "Some traction on slide 5."},
        },
        strengths=["Clear problem statement."],
        weaknesses=["No unit economics disclosed."],
        action_items=["Add traction metrics.", "Clarify the ask.", "Expand GTM detail."],
        input_tokens=1000,
        output_tokens=500,
        estimated_cost_usd=0.05,
    )


def test_build_result_email_html_includes_key_fields():
    html = build_result_email_html(make_analysis())

    assert "deck.pdf" in html
    assert "72.5" in html
    assert "Team &amp; Execution Capability" in html
    assert "Slide 3 shows a strong team." in html
    assert "Clear problem statement." in html
    assert "No unit economics disclosed." in html
    assert "Add traction metrics." in html


def test_build_result_email_html_escapes_untrusted_content():
    analysis = make_analysis()
    analysis.strengths = ["<script>alert(1)</script>"]

    html = build_result_email_html(analysis)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


@patch("app.notifications.email.resend")
@patch("app.notifications.email.get_settings")
def test_send_result_email_calls_resend_when_configured(mock_get_settings, mock_resend):
    mock_get_settings.return_value = MagicMock(
        resend_api_key="re_test",
        resend_from_email="onboarding@resend.dev",
        results_email_to="mateo.ghercioiu@gmail.com",
    )

    send_result_email(make_analysis())

    mock_resend.Emails.send.assert_called_once()
    call_kwargs = mock_resend.Emails.send.call_args[0][0]
    assert call_kwargs["to"] == ["mateo.ghercioiu@gmail.com"]
    assert call_kwargs["from"] == "onboarding@resend.dev"
    assert "deck.pdf" in call_kwargs["subject"]


@patch("app.notifications.email.resend")
@patch("app.notifications.email.get_settings")
def test_send_result_email_skips_when_no_api_key(mock_get_settings, mock_resend):
    mock_get_settings.return_value = MagicMock(resend_api_key="")

    send_result_email(make_analysis())

    mock_resend.Emails.send.assert_not_called()


@patch("app.notifications.email.resend")
@patch("app.notifications.email.get_settings")
def test_send_result_email_swallows_send_failures(mock_get_settings, mock_resend):
    mock_get_settings.return_value = MagicMock(
        resend_api_key="re_test",
        resend_from_email="onboarding@resend.dev",
        results_email_to="mateo.ghercioiu@gmail.com",
    )
    mock_resend.Emails.send.side_effect = RuntimeError("resend is down")

    send_result_email(make_analysis())  # must not raise
