from typing import Optional, Dict, Any
from .pdf_loader import load_pdf
from .chunking import chunk_text
from .llm import summarize_chunk, consolidate_summaries


def summarize_document(path: str, focus: Optional[str] = None, *, chunk_size: int = 3000, chunk_overlap: int = 300) -> Dict[str, Any]:  # noqa: E501
    pages = load_pdf(path)
    chunks = chunk_text(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    partial = [summarize_chunk(c, focus=focus) for c in chunks]
    final = consolidate_summaries(partial, focus=focus)
    return {
        "pages": len(pages),
        "chunks": len(chunks),
        "partial_summaries": partial,
        "final_summary": final,
    }
