from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import get_settings

settings = get_settings()


def _normalize_database_url(url: str) -> str:
    """Railway (and Heroku) inject DATABASE_URL with the legacy 'postgres://'
    scheme, which SQLAlchemy's psycopg2 dialect rejects - normalize it."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


DATABASE_URL = _normalize_database_url(settings.database_url)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    """One uploaded deck and its extraction/scoring lifecycle.

    Scoring fields are nullable and populated by the stage (b)/(c) pipeline;
    a row exists as soon as extraction succeeds so a user can see it in their
    history even before scoring completes.
    """

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    filename: Mapped[str] = mapped_column(String(512))
    source_format: Mapped[str] = mapped_column(String(16))
    slide_count: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(32), default="extracted")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    overall_score: Mapped[float | None] = mapped_column(nullable=True)
    category_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strengths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    weaknesses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    action_items: Mapped[list | None] = mapped_column(JSON, nullable=True)

    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
