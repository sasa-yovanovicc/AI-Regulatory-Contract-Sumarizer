from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import tempfile
from summarizer.pdf_loader import load_pdf
from summarizer.chunking import chunk_text
from summarizer.llm import (
    analyze_chunk,
    consolidate_task_outputs,
)
from typing import Optional, List, Iterable
from dotenv import load_dotenv
import os

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    # Not fatal for health endpoint, but warn in logs
    print("[WARN] OPENAI_API_KEY not set – LLM endpoints will fail until configured.")


app = FastAPI(title="Regulatory Summarizer API", version="0.1.0")

# -------------------------------------------------------------
# CORS (frontend dev runs on a different port e.g. 5173)
# -------------------------------------------------------------
origins_env = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
origins = [o.strip() for o in origins_env.split(",") if o.strip()]
# Support wildcard shortcut
allow_origins = ["*"] if any(o == "*" for o in origins) else origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/debug/routes")
def debug_routes():
    return [r.path for r in app.routes]


@app.get("/debug/test-stream")
def test_stream():
    from fastapi.responses import StreamingResponse
    def simple_gen():
        yield '{"test": "line1"}\n'
        yield '{"test": "line2"}\n'
    return StreamingResponse(simple_gen(), media_type="application/x-ndjson")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


class SummarizeRequest(BaseModel):
    focus: Optional[str] = None
    chunk_size: int = 3000
    chunk_overlap: int = 300
    task: str = "summary"  # summary | unfavorable_elements | conflicts
    text: Optional[str] = None  # optional raw text alternative to PDF upload


@app.post("/summarize")
async def summarize(req: SummarizeRequest):
    if req.text:
        pages = [req.text]
    else:
        raise HTTPException(status_code=400, detail="Provide 'text' or use /summarize-pdf endpoint")
    chunks = chunk_text(pages, chunk_size=req.chunk_size, chunk_overlap=req.chunk_overlap)
    outputs = [analyze_chunk(c, task=req.task) for c in chunks]
    final = consolidate_task_outputs(outputs, task=req.task, focus=req.focus)
    return {
        "chunks": len(chunks),
        "task": req.task,
        "partial": outputs,
        "final": final,
    }


def _ndjson_iter(items: Iterable[str]):  # small helper
    for it in items:
        yield it if it.endswith("\n") else it + "\n"


def _stream_process(chunks: List[str], task: str, focus: Optional[str]):
    import json, time
    start = time.time()
    debug = os.getenv("DEBUG_STREAM", "0") == "1"
    if debug:
        print(f"[STREAM] start task={task} chunks={len(chunks)} focus={focus}")
    try:
        yield json.dumps({"type": "meta", "chunks": len(chunks), "task": task})
        partial_outputs: List[str] = []
        for idx, c in enumerate(chunks, 1):
            t0 = time.time()
            try:
                out = analyze_chunk(c, task=task)
            except Exception as e:  # send error event and continue/abort
                if debug:
                    print(f"[STREAM] chunk {idx} ERROR: {e}")
                yield json.dumps({"type": "error", "chunk": idx, "message": str(e)})
                break
            dt = time.time() - t0
            partial_outputs.append(out)
            if debug:
                print(f"[STREAM] chunk {idx}/{len(chunks)} dt={dt:.2f}s")
            yield json.dumps({
                "type": "chunk",
                "index": idx,
                "elapsed_chunk_sec": round(dt, 3),
                "content": out,
                "processed": idx,
                "total": len(chunks),
            })
        if partial_outputs:
            try:
                final = consolidate_task_outputs(partial_outputs, task=task, focus=focus)
                if debug:
                    print(f"[STREAM] final produced in {time.time()-start:.2f}s")
                yield json.dumps({
                    "type": "final",
                    "final": final,
                    "processed": len(partial_outputs),
                    "total": len(chunks),
                    "elapsed_total_sec": round(time.time() - start, 3),
                })
            except Exception as e:
                if debug:
                    print(f"[STREAM] finalization ERROR: {e}")
                yield json.dumps({"type": "error", "message": f"finalization failed: {e}"})
    except Exception as e:
        if debug:
            print(f"[STREAM] FATAL ERROR: {e}")
        yield json.dumps({"type": "error", "message": f"stream failed: {e}"})


@app.post("/summarize-stream")
async def summarize_stream(req: SummarizeRequest):
    if not req.text:
        raise HTTPException(status_code=400, detail="text field required for streaming")
    pages = [req.text]
    chunks = chunk_text(pages, chunk_size=req.chunk_size, chunk_overlap=req.chunk_overlap)
    # Fallback: return all results at once instead of streaming
    try:
        outputs = [analyze_chunk(c, task=req.task) for c in chunks]
        final = consolidate_task_outputs(outputs, task=req.task, focus=req.focus)
        return {
            "type": "complete",
            "chunks": len(chunks),
            "task": req.task,
            "partial": outputs,
            "final": final
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.post("/summarize-pdf-stream")
async def summarize_pdf_stream(
    file: UploadFile = File(...),
    task: str = Form("summary"),
    focus: Optional[str] = Form(None),
    chunk_size: int = Form(3000),
    chunk_overlap: int = Form(300),
):
    # Debug logging
    debug = os.getenv("DEBUG_STREAM", "0") == "1"
    if debug:
        print(f"[API] Received task={task}, focus={focus}")
    
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF supported")
    
    # Save uploaded file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        tmp.write(content)
        path = tmp.name
    
    try:
        pages = load_pdf(path)
        if not pages:
            raise HTTPException(status_code=400, detail="PDF contains no extractable text")
        
        chunks = chunk_text(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        # Limit chunks for large documents to avoid timeout/rate limits
        max_chunks = int(os.getenv("MAX_CHUNKS", "20"))
        if len(chunks) > max_chunks:
            chunks = chunks[:max_chunks]
            print(f"[WARN] PDF too large, processing only first {max_chunks} chunks")
        
        outputs = []
        for i, c in enumerate(chunks):
            try:
                out = analyze_chunk(c, task=task)
                outputs.append(out)
                # Small delay between API calls to avoid rate limits
                if i < len(chunks) - 1:  # not last chunk
                    import time
                    time.sleep(0.5)
            except Exception as e:
                error_msg = str(e)
                if "rate" in error_msg.lower() or "quota" in error_msg.lower():
                    # Stop processing on rate/quota issues
                    outputs.append(f"[Stopped at chunk {i+1}/{len(chunks)} due to rate limit]")
                    break
                else:
                    outputs.append(f"[Error in chunk {i+1}: {error_msg}]")
        
        if outputs:
            final = consolidate_task_outputs(outputs, task=task, focus=focus)
        else:
            final = "No content could be processed"
        
        return {
            "type": "complete", 
            "pages": len(pages),
            "chunks": len(chunks),
            "processed_chunks": len(outputs),
            "task": task,
            "partial": outputs,
            "final": final
        }
    except HTTPException:
        raise  # re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF processing failed: {str(e)}")
    finally:
        try:
            os.unlink(path)  # cleanup temp file
        except:
            pass


@app.post("/summarize-pdf")
async def summarize_pdf(
    focus: Optional[str] = None,
    chunk_size: int = 3000,
    chunk_overlap: int = 300,
    task: str = "summary",
    file: UploadFile = File(...),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF supported")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        path = tmp.name
    try:
        pages = load_pdf(path)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(e))
    chunks = chunk_text(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    outputs = [analyze_chunk(c, task=task) for c in chunks]
    final = consolidate_task_outputs(outputs, task=task, focus=focus)
    return {
        "pages": len(pages),
        "chunks": len(chunks),
        "task": task,
        "final": final,
    }


@app.get("/tasks")
def list_tasks():
    return ["summary", "unfavorable_elements", "conflicts"]


class BatchAnalyzeRequest(BaseModel):
    task: str
    fragments: List[str]
    focus: Optional[str] = None


@app.post("/analyze-batch")
def analyze_batch(req: BatchAnalyzeRequest):
    if not req.fragments:
        raise HTTPException(status_code=400, detail="fragments cannot be empty")
    outputs = [analyze_chunk(f, task=req.task) for f in req.fragments]
    final = consolidate_task_outputs(outputs, task=req.task, focus=req.focus)
    return {"count": len(outputs), "task": req.task, "final": final}


@app.exception_handler(Exception)
async def generic_handler(request, exc):  # pragma: no cover
    return JSONResponse(status_code=500, content={"error": str(exc)})
