from summarizer.llm import summarize_chunk
import os
import pytest

@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="No API key")
def test_summarize_chunk_smoke(monkeypatch):
    # If API key present, do a tiny call
    out = summarize_chunk("Ovo je kratak test regulatornog teksta.")
    assert isinstance(out, str)
    assert len(out) > 0
