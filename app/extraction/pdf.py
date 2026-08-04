import fitz  # PyMuPDF

from app.extraction.normalize import Deck, DeckExtractionError, Slide

# Below this average characters-per-page, a PDF is almost certainly scanned
# images rather than real text - flag it clearly instead of silently scoring
# an empty deck. OCR is a stretch goal, not implemented in v1.
SCANNED_PDF_CHAR_THRESHOLD_PER_PAGE = 20


def extract_pdf(file_bytes: bytes, filename: str) -> Deck:
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise DeckExtractionError(
            f"Could not open '{filename}' as a PDF. The file may be corrupted "
            f"or not a valid PDF."
        ) from e

    if doc.page_count == 0:
        raise DeckExtractionError(f"'{filename}' has no pages.")

    slides: list[Slide] = []
    for i, page in enumerate(doc):
        try:
            text = page.get_text("text")
        except Exception as e:
            raise DeckExtractionError(
                f"Failed to extract text from page {i + 1} of '{filename}'."
            ) from e
        slides.append(Slide(index=i + 1, text_blocks=[text]))

    deck = Deck(filename=filename, source_format="pdf", slides=slides)

    avg_chars_per_page = deck.total_text_length / max(deck.slide_count, 1)
    if avg_chars_per_page < SCANNED_PDF_CHAR_THRESHOLD_PER_PAGE:
        raise DeckExtractionError(
            f"'{filename}' appears to contain little or no extractable text "
            f"(average {avg_chars_per_page:.0f} chars/page). This usually means "
            f"the PDF is a scan or image export rather than text. OCR support "
            f"is not available yet - please upload a text-based export of the deck."
        )

    return deck
