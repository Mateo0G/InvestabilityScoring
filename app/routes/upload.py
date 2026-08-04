import logging
import uuid

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.extraction.normalize import DeckExtractionError
from app.extraction.pdf import extract_pdf
from app.extraction.pptx import extract_pptx
from app.models.db import Analysis, get_db
from app.scoring.pipeline import run_scoring_pipeline
from app.scoring.rubric import CATEGORIES, category_by_key

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["category_label"] = lambda key: category_by_key(key).label
templates.env.globals["category_weight"] = lambda key: category_by_key(key).weight

SESSION_COOKIE_NAME = "session_id"


def get_or_create_session_id(request: Request) -> str:
    return request.cookies.get(SESSION_COOKIE_NAME) or str(uuid.uuid4())


@router.get("/", response_class=HTMLResponse)
def upload_form(request: Request, db: Session = Depends(get_db)):
    session_id = get_or_create_session_id(request)
    analyses = (
        db.query(Analysis)
        .filter(Analysis.session_id == session_id)
        .order_by(Analysis.created_at.desc())
        .all()
    )
    response = templates.TemplateResponse(
        "upload.html", {"request": request, "analyses": analyses, "error": None}
    )
    response.set_cookie(SESSION_COOKIE_NAME, session_id, httponly=True, samesite="lax")
    return response


@router.post("/upload", response_class=HTMLResponse)
async def upload_deck(request: Request, file: UploadFile, db: Session = Depends(get_db)):
    session_id = get_or_create_session_id(request)
    settings = get_settings()

    filename = file.filename or "deck"
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if suffix not in ("pdf", "pptx"):
        return _render_error(
            request, db, session_id,
            f"Unsupported file type '.{suffix}'. Please upload a PDF or PPTX file.",
        )

    file_bytes = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        return _render_error(
            request, db, session_id,
            f"File is too large ({len(file_bytes) / 1024 / 1024:.1f} MB). "
            f"Max upload size is {settings.max_upload_mb} MB.",
        )

    try:
        if suffix == "pdf":
            deck = extract_pdf(file_bytes, filename)
        else:
            deck = extract_pptx(file_bytes, filename)
    except DeckExtractionError as e:
        return _render_error(request, db, session_id, e.message)

    analysis = Analysis(
        session_id=session_id,
        filename=deck.filename,
        source_format=deck.source_format,
        slide_count=deck.slide_count,
        extracted_text=deck.to_prompt_text(),
        status="extracted",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    try:
        pipeline_result = run_scoring_pipeline(deck, deck.filename)
    except Exception as e:
        logger.exception("Scoring pipeline failed for analysis %d", analysis.id)
        analysis.status = "scoring_failed"
        analysis.error_message = (
            "Scoring failed - this is usually a temporary Claude API issue "
            f"(rate limit, timeout, or invalid API key). Details: {e}"
        )
    else:
        analysis.status = "complete"
        analysis.overall_score = pipeline_result.overall_score
        analysis.category_scores = {
            cs.key: {"score": cs.score, "justification": cs.justification}
            for cs in pipeline_result.analysis_result.category_scores
        }
        analysis.strengths = pipeline_result.analysis_result.strengths
        analysis.weaknesses = pipeline_result.analysis_result.weaknesses
        analysis.action_items = pipeline_result.analysis_result.action_items
        analysis.input_tokens = pipeline_result.total_input_tokens
        analysis.output_tokens = pipeline_result.total_output_tokens
        analysis.estimated_cost_usd = pipeline_result.total_cost_usd

    db.commit()

    response = RedirectResponse(url=f"/analyses/{analysis.id}", status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, session_id, httponly=True, samesite="lax")
    return response


@router.get("/analyses/{analysis_id}", response_class=HTMLResponse)
def view_analysis(analysis_id: int, request: Request, db: Session = Depends(get_db)):
    session_id = get_or_create_session_id(request)
    analysis = (
        db.query(Analysis)
        .filter(Analysis.id == analysis_id, Analysis.session_id == session_id)
        .first()
    )
    if analysis is None:
        return _render_error(request, db, session_id, "Analysis not found.", status_code=404)

    response = templates.TemplateResponse(
        "analysis.html", {"request": request, "analysis": analysis, "categories": CATEGORIES}
    )
    response.set_cookie(SESSION_COOKIE_NAME, session_id, httponly=True, samesite="lax")
    return response


def _render_error(request: Request, db: Session, session_id: str, message: str, status_code: int = 200):
    analyses = (
        db.query(Analysis)
        .filter(Analysis.session_id == session_id)
        .order_by(Analysis.created_at.desc())
        .all()
    )
    response = templates.TemplateResponse(
        "upload.html",
        {"request": request, "analyses": analyses, "error": message},
        status_code=status_code,
    )
    response.set_cookie(SESSION_COOKIE_NAME, session_id, httponly=True, samesite="lax")
    return response
