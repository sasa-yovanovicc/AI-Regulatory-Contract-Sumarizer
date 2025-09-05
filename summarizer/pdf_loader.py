from typing import List

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore


def load_pdf(path: str) -> List[str]:
    """Extract text per page from a PDF using PyMuPDF (fitz).

    Raises:
        RuntimeError: if PyMuPDF is not installed in current environment.
    """
    if fitz is None:
        raise RuntimeError("PyMuPDF (pymupdf) is not installed. Run 'pip install pymupdf'.")
    doc = fitz.open(path)
    pages = []
    try:
        for page in doc:
            text = page.get_text("text")
            if text:
                pages.append(text)
    finally:
        doc.close()
    return pages
