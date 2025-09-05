import os
from summarizer.pdf_loader import load_pdf

# Minimal smoke test placeholder (can't parse without a sample PDF)

def test_loader_no_file():
    # Expect an exception if file missing
    try:
        load_pdf("nonexistent.pdf")
    except Exception as e:
        assert isinstance(e, Exception)
    else:
        assert False, "Expected exception for missing file"
