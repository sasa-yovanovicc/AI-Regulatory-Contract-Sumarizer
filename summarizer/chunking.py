from typing import List
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore
except ImportError:  # pragma: no cover
    RecursiveCharacterTextSplitter = None  # type: ignore


def chunk_text(pages: List[str], chunk_size: int = 3000, chunk_overlap: int = 300) -> List[str]:
    joined = "\n".join(pages)
    if RecursiveCharacterTextSplitter is None:
        # Very simple fallback: naive slicing with overlap
        raw_chunks = []
        start = 0
        while start < len(joined):
            end = start + chunk_size
            raw_chunks.append(joined[start:end])
            start = end - chunk_overlap
    else:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", ".", "?", "!", " "]
        )
        raw_chunks = [c.strip() for c in splitter.split_text(joined) if c.strip()]
    trimmed: List[str] = []
    for c in raw_chunks:
        if len(c) > chunk_size:
            # Hard trim but try to end at a sentence boundary near limit
            candidate = c[:chunk_size]
            last_period = candidate.rfind('.')
            if last_period > chunk_size * 0.6:
                candidate = candidate[: last_period + 1]
            trimmed.append(candidate.strip())
        else:
            trimmed.append(c)
    return trimmed
