"""Scoring rubric: categories, weights, and descriptions used to build the
Claude system prompt and to validate/aggregate the structured response.

Weights are a plain config, not magic numbers scattered through the pipeline.
Adjust here to retune the Investability Score without touching prompts or
validation logic. Weights must sum to 100.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    weight: int
    description: str


CATEGORIES: tuple[Category, ...] = (
    Category(
        key="team_execution",
        label="Team & Execution Capability",
        weight=15,
        description=(
            "Founder/team background, relevant domain expertise, prior execution "
            "track record, completeness of the founding team for what the business needs."
        ),
    ),
    Category(
        key="traction_validation",
        label="Traction & Validation",
        weight=15,
        description=(
            "Concrete evidence the product/market fit hypothesis is being validated: "
            "revenue, users, growth rate, pilots, LOIs, retention, case studies."
        ),
    ),
    Category(
        key="business_model_unit_economics",
        label="Business Model & Unit Economics",
        weight=12,
        description=(
            "Clarity of the revenue model, pricing logic, and unit economics "
            "(CAC, LTV, margins, payback) where disclosed or inferable."
        ),
    ),
    Category(
        key="problem_market_clarity",
        label="Problem/Market Clarity",
        weight=10,
        description=(
            "How clearly and credibly the deck articulates the problem, who has it, "
            "and why it matters now."
        ),
    ),
    Category(
        key="solution_differentiation",
        label="Solution/Product Differentiation",
        weight=10,
        description=(
            "Clarity of the solution and how it is meaningfully differentiated "
            "from alternatives, not just a feature list."
        ),
    ),
    Category(
        key="go_to_market",
        label="Go-to-Market Strategy",
        weight=10,
        description=(
            "Credibility and specificity of the customer acquisition/distribution "
            "plan, beyond generic 'sales and marketing' statements."
        ),
    ),
    Category(
        key="market_sizing",
        label="Market Sizing (TAM/SAM/SOM) Rigor",
        weight=8,
        description=(
            "Methodological rigor behind TAM/SAM/SOM figures - bottom-up vs. "
            "unsupported top-down claims."
        ),
    ),
    Category(
        key="competitive_positioning",
        label="Competitive Positioning",
        weight=8,
        description=(
            "Honesty and specificity of the competitive landscape and the "
            "company's defensible position within it."
        ),
    ),
    Category(
        key="financials_ask_clarity",
        label="Financials & Ask Clarity",
        weight=7,
        description=(
            "Clarity of the financial projections, the ask (amount, use of funds), "
            "and whether the numbers are internally consistent."
        ),
    ),
    Category(
        key="fundraise_narrative_coherence",
        label="Fundraise Narrative Coherence",
        weight=5,
        description=(
            "Whether the deck tells one coherent story end-to-end, or whether "
            "sections contradict each other (e.g. market size vs. ask vs. traction)."
        ),
    ),
)

_TOTAL_WEIGHT = sum(c.weight for c in CATEGORIES)
assert _TOTAL_WEIGHT == 100, f"Rubric weights must sum to 100, got {_TOTAL_WEIGHT}"


def category_by_key(key: str) -> Category:
    for c in CATEGORIES:
        if c.key == key:
            return c
    raise KeyError(f"Unknown rubric category: {key}")
