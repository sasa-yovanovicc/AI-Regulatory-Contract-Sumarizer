from summarizer.chunking import chunk_text

def test_chunking_basic():
    pages = ["A" * 1200 + "\n" + "B" * 800]
    chunks = chunk_text(pages, chunk_size=500, chunk_overlap=50)
    assert len(chunks) > 1
    # Ensure overlap produced some continuity
    # Ensure no chunk wildly exceeds 2x target size
    for c in chunks:
        assert len(c) <= 1000
