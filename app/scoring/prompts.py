"""Prompt construction for the scoring pipeline.

The rubric portion is large and identical across every request, so it is kept
as a separate, stable block with a cache_control breakpoint - see
client.py, which is where it actually gets attached to the request.
"""

from app.scoring.rubric import CATEGORIES

_CATEGORY_LINES = "\n".join(
    f"- {c.key} ({c.label}, weight {c.weight}%): {c.description}" for c in CATEGORIES
)

SCORING_SYSTEM_PROMPT = f"""You are an experienced venture capital investment analyst. You will be given
the full extracted text of a startup pitch deck, labeled slide-by-slide, and must score its
investment readiness against a fixed rubric.

Rubric categories (score each 0-100):
{_CATEGORY_LINES}

Rules you must follow:
1. Ground every justification in specific content actually present in the deck - reference the
   slide number and the specific claim, number, or statement you are evaluating. Do not invent
   information that is not in the deck.
2. If a category is not addressed in the deck at all, score it low and say so explicitly in the
   justification - do not guess or fabricate content to fill the gap.
3. Strengths and weaknesses must each reference specific deck content, not generic startup advice.
4. Action items must be the 3-5 highest-priority, most specific changes the founder should make
   before approaching institutional investors - ordered by priority, most important first.
5. Do not repeat the same point across strengths, weaknesses, and action items - each section
   should surface distinct information.
"""


def build_scoring_user_prompt(deck_text: str, filename: str) -> str:
    return (
        f"Pitch deck filename: {filename}\n\n"
        f"Extracted deck content (slide-by-slide):\n\n{deck_text}\n\n"
        "Score this deck now against the rubric above."
    )
