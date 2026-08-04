"""Shared data shapes produced by the PDF and PPTX extractors."""

from dataclasses import dataclass, field


class DeckExtractionError(Exception):
    """Raised when a deck cannot be parsed into usable text.

    Carries a user-facing message so routes can surface a clear error
    instead of a raw traceback or a silent empty result.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class Slide:
    index: int
    text_blocks: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def text(self) -> str:
        return "\n".join(b for b in self.text_blocks if b.strip())

    @property
    def is_empty(self) -> bool:
        return not self.text.strip() and not self.notes.strip()


@dataclass
class Deck:
    filename: str
    source_format: str  # "pdf" | "pptx"
    slides: list[Slide]

    @property
    def slide_count(self) -> int:
        return len(self.slides)

    @property
    def non_empty_slide_count(self) -> int:
        return sum(1 for s in self.slides if not s.is_empty)

    @property
    def total_text_length(self) -> int:
        return sum(len(s.text) for s in self.slides)

    def to_prompt_text(self) -> str:
        """Render the deck as a single slide-labeled block for the Claude prompt."""
        parts = []
        for slide in self.slides:
            if slide.is_empty:
                continue
            block = f"--- Slide {slide.index} ---\n{slide.text}"
            if slide.notes.strip():
                block += f"\n[Speaker notes: {slide.notes.strip()}]"
            parts.append(block)
        return "\n\n".join(parts)
