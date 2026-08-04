# Investor Scoring

Analyzes startup pitch decks (PDF/PPTX) and produces an Investment Readiness Score.

**Status:** All five stages complete — upload, extraction, Claude scoring pipeline, a full dark-themed
results UI, and Railway deployment config are all in place. Calibrated against two real pitch decks
(a consumer/SaaS marketplace deck and a B2B education hardware deck) - scores were well
differentiated (60.1 vs 74.5), every justification cited a specific slide/figure, and the
model caught real internal inconsistencies (e.g. "zero marketing spend" traction claims next
to a 40%-to-GTM use-of-funds slide) without any prompt tuning needed.

## Scoring rubric (locked in)

Ten categories, weighted (see `app/scoring/rubric.py` to adjust):

| Category | Weight |
|---|---|
| Team & Execution Capability | 15% |
| Traction & Validation | 15% |
| Business Model & Unit Economics | 12% |
| Problem/Market Clarity | 10% |
| Solution/Product Differentiation | 10% |
| Go-to-Market Strategy | 10% |
| Market Sizing (TAM/SAM/SOM) Rigor | 8% |
| Competitive Positioning | 8% |
| Financials & Ask Clarity | 7% |
| Fundraise Narrative Coherence | 5% |

Assumes a generalist seed–Series A lens; retune weights for growth-stage decks.

## Local development

Requires Python 3.12 (pydantic-core has no prebuilt wheels for 3.14 yet on Windows,
and building from source needs a working Rust/MSVC linker setup).

```bash
py -3.12 -m venv .venv
./.venv/Scripts/pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY when scoring is wired up
./.venv/Scripts/python -m uvicorn app.main:app --reload
```

Visit http://127.0.0.1:8000/, upload a PDF or PPTX pitch deck. Extraction + scoring results
persist per-browser-session (cookie-based, no login) in a local SQLite DB
(`investor_scoring.db`). Without a real `ANTHROPIC_API_KEY`, upload still works and extraction
still succeeds — the analysis page shows a clean "scoring failed" error instead of a score.

Run tests:

```bash
./.venv/Scripts/python -m pytest tests/ -v
```

## Deploying to Railway

1. Push this repo to GitHub, then in Railway: **New Project → Deploy from GitHub repo**.
2. Add a **Postgres** plugin to the project (Railway → **+ New → Database → PostgreSQL**).
   Railway injects `DATABASE_URL` into your app service automatically - no manual wiring
   needed. (`app/models/db.py` normalizes Railway/Heroku's legacy `postgres://` scheme to
   `postgresql://`, which SQLAlchemy's psycopg2 dialect requires.)
3. In the app service's **Variables** tab, set:
   - `ANTHROPIC_API_KEY` — required.
   - `CLAUDE_EXTRACTION_MODEL` / `CLAUDE_SCORING_MODEL` — optional, defaults match `.env.example`.
   - `MAX_UPLOAD_MB` — optional, default 25.
   - `RESEND_API_KEY` — optional. If unset, result emails are silently skipped (logged, never
     blocks scoring). Get one from [resend.com](https://resend.com).
   - `RESEND_FROM_EMAIL` — optional, defaults to Resend's sandbox sender `onboarding@resend.dev`
     (works without a verified domain, but Resend only delivers it to the email address on the
     Resend account itself). Set to a verified-domain address for real production sending.
   - `RESULTS_EMAIL_TO` — optional, defaults to `mateo.ghercioiu@gmail.com`.
   - Do **not** set `DATABASE_URL` yourself - the Postgres plugin provides it.
4. Railway builds via Nixpacks using `runtime.txt` (pins Python 3.12 - `pydantic-core` has no
   prebuilt wheel for 3.14 yet) and `requirements.txt`, then runs the command in `Procfile` /
   `railway.json` (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`) - `$PORT` is injected by
   Railway, never hardcode a port.
5. On first deploy, `init_db()` (FastAPI startup hook) calls `Base.metadata.create_all()`
   against Postgres, creating the `analyses` table. There's no Alembic migration setup yet -
   fine for a fresh deploy; add migrations before you need to evolve the schema without
   dropping data.
6. Deploys are stateless/ephemeral - SQLite (`investor_scoring.db`) is for local dev only and
   won't persist across Railway restarts. Production always runs on the Postgres plugin.

## What's implemented so far

- PDF extraction via PyMuPDF (`app/extraction/pdf.py`), with a heuristic to flag
  scanned/image-only PDFs (no OCR in v1).
- PPTX extraction via python-pptx (`app/extraction/pptx.py`), including table text,
  chart titles, and speaker notes; flags image-only decks.
- Slide-by-slide normalized structure (`app/extraction/normalize.py`) that renders to
  a single labeled text block for later use as the Claude prompt.
- SQLAlchemy models (`app/models/db.py`) with scoring fields (overall score, category
  scores, strengths/weaknesses/action items, token usage, estimated cost).
- Claude scoring pipeline (`app/scoring/`):
  - `rubric.py` — the 10 weighted categories (single source of truth for prompt + aggregation).
  - `prompts.py` — the rubric-grounded system prompt (cached via `cache_control`) and per-deck
    user prompt.
  - `client.py` — model-routed calls: Haiku (`claude-haiku-4-5-20251001`) classifies slides
    into rubric categories; Sonnet (`claude-sonnet-5`) does the scoring judgment via
    `client.messages.parse(output_format=AnalysisResult)`. Retries transient API errors
    (rate limit/connection/5xx) via `tenacity`, and retries with a corrective follow-up
    message if the parsed output fails pydantic validation.
  - `pricing.py` — per-token cost estimator for usage logging.
  - `pipeline.py` — orchestrates classify → score → deterministic server-side weighted
    aggregation (the overall score is computed in code, never trusted from the model).
- Upload route calls the pipeline synchronously after extraction and persists results;
  a failed Claude call is caught and shown as a clean error without losing the extraction.
- Dark-themed Jinja2 UI (`app/templates/`): upload form (file-attached confirmation with a
  remove/clear control, scoring-in-progress state with a spinner), session history, extraction
  preview, full results page with a horizontal bar chart for the category breakdown (score,
  weight, justification per category), strengths/weaknesses, prioritized action items,
  token/cost usage.
- Result notification email (`app/notifications/email.py`): on successful scoring, sends an
  HTML summary (score, category breakdown, strengths/weaknesses/action items) via Resend to
  `RESULTS_EMAIL_TO`. Best-effort - missing API key or a Resend failure is logged and never
  blocks or fails the scoring request.
- 20 tests, all Claude API and Resend calls mocked (`tests/test_scoring_pipeline.py`,
  `tests/test_extraction.py`, `tests/test_email.py`) — no real API keys needed to run the suite.
- Railway deployment config: `Procfile`, `railway.json`, `runtime.txt` (pins Python 3.12),
  `DATABASE_URL` normalization for Postgres in `app/models/db.py`.

## Known gaps / assumptions to revisit

- **No real logo asset.** The UI uses a placeholder gradient mark in the "Investor Scoring"
  badge - swap in the real Ten Capital Network logo file when available.
- **No Alembic migrations.** Schema changes currently require a fresh `create_all()` - fine
  pre-launch, add Alembic before you need to evolve the Postgres schema without data loss.
- **Synchronous scoring in the request/response cycle.** A slow/rate-limited Claude call blocks
  the HTTP request; fine for single-user MVP traffic, but move to a background job/queue if
  concurrent uploads become common.
- **No PDF/DOCX export of results** - deferred per your original "on-screen only for v1" call.
