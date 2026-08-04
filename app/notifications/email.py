import html
import logging

import resend

from app.config import get_settings
from app.models.db import Analysis
from app.scoring.rubric import CATEGORIES

logger = logging.getLogger(__name__)


def _esc(value: str) -> str:
    return html.escape(value, quote=False)


def build_result_email_html(analysis: Analysis) -> str:
    category_rows = ""
    for c in CATEGORIES:
        cs = (analysis.category_scores or {}).get(c.key)
        if not cs:
            continue
        category_rows += f"""
        <tr>
          <td style="padding:8px 12px; border-bottom:1px solid #e5e7eb;">{_esc(c.label)}
            <div style="color:#8b93a7; font-size:12px;">weight {c.weight}%</div>
          </td>
          <td style="padding:8px 12px; border-bottom:1px solid #e5e7eb; text-align:right; font-weight:700;">
            {cs['score']}/100
          </td>
        </tr>
        <tr>
          <td colspan="2" style="padding:0 12px 12px; color:#4b5563; font-size:13px;">
            {_esc(cs['justification'])}
          </td>
        </tr>
        """

    strengths = "".join(f"<li>{_esc(s)}</li>" for s in (analysis.strengths or []))
    weaknesses = "".join(f"<li>{_esc(w)}</li>" for w in (analysis.weaknesses or []))
    action_items = "".join(f"<li>{_esc(a)}</li>" for a in (analysis.action_items or []))

    return f"""
    <div style="font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 640px; margin: 0 auto; color:#1a1a2e;">
      <h2 style="margin-bottom:4px;">Investment Readiness Score</h2>
      <p style="color:#6b7280; margin-top:0;">{_esc(analysis.filename)}</p>

      <div style="background:#f4645f; background-image: linear-gradient(90deg, #f4645f, #f5a742);
                  color:#1a1208; border-radius:10px; padding:20px; text-align:center; margin:16px 0;">
        <div style="font-size:13px; text-transform:uppercase; letter-spacing:0.08em;">Overall Score</div>
        <div style="font-size:40px; font-weight:700;">{analysis.overall_score}<span style="font-size:18px;">/100</span></div>
      </div>

      <h3>Category Breakdown</h3>
      <table style="width:100%; border-collapse:collapse;">
        {category_rows}
      </table>

      <h3>Strengths</h3>
      <ul>{strengths}</ul>

      <h3>Weaknesses</h3>
      <ul>{weaknesses}</ul>

      <h3>Fix These Before You Pitch Investors</h3>
      <ol>{action_items}</ol>

      <p style="color:#9ca3af; font-size:12px; margin-top:24px;">
        Claude usage: {analysis.input_tokens} input tokens, {analysis.output_tokens} output tokens,
        estimated cost ${analysis.estimated_cost_usd:.4f}
      </p>
    </div>
    """


def send_result_email(analysis: Analysis) -> None:
    """Best-effort notification email - never raises. A failure here should
    never take down an otherwise-successful scoring request."""
    settings = get_settings()
    if not settings.resend_api_key:
        logger.info("RESEND_API_KEY not set - skipping result email for analysis %d", analysis.id)
        return

    resend.api_key = settings.resend_api_key
    try:
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": [settings.results_email_to],
            "subject": f"Investability Score: {analysis.filename} ({analysis.overall_score}/100)",
            "html": build_result_email_html(analysis),
        })
        logger.info("Sent result email for analysis %d to %s", analysis.id, settings.results_email_to)
    except Exception:
        logger.exception("Failed to send result email for analysis %d", analysis.id)
