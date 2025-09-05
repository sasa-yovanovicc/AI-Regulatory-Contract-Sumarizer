# Regulatory Summarizer & Analyzer

LLM-powered summarization and analysis for long regulatory or contractual PDFs (GDPR, EBA guidelines, policies, contracts) producing concise outputs for banking and compliance staff.

## Core capabilities
* PDF ingestion and text extraction (PyMuPDF)
* Smart chunking (LangChain recursive splitter + hard length enforcement)
* Per-chunk LLM analysis with task-specific templates
* Consolidation into an executive summary or structured risk lists
* Tasks:
	* **summary** – executive overview
	* **unfavorable_elements** – potentially unfavorable or high-risk clauses
	* **conflicts** – internally conflicting or inconsistent sections

## Architecture
```
FastAPI (REST) ← React (Vite) Frontend
								|
								v
PDF → pdf_loader → chunking → analyze_chunk(task) → consolidate_task_outputs
```
No vector database (not full RAG). Pure upload plus structured prompting.

## Backend (FastAPI)
**Endpoints:**
- `GET  /health` → health probe
- `GET  /tasks` → list supported tasks
- `POST /summarize` → JSON body (raw text)
- `POST /summarize-pdf` → multipart (PDF file)
- `POST /summarize-pdf-stream` → streaming PDF analysis
- `POST /analyze-batch` → batch fragments (JSON)

All data-returning operations are POST. Service/status endpoints are GET.

## Running the API
**Development (auto-reload):**
```bash
python -m venv .venv
. .venv/Scripts/activate  # PowerShell
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --reload --port 8000
```
**Basic production style:**
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Example curl calls
**Health check:**
```bash
curl http://localhost:8000/health
```
**List tasks:**
```bash
curl http://localhost:8000/tasks
```
**Summarize raw text:**
```bash
curl -X POST http://localhost:8000/summarize -H "Content-Type: application/json" \
	-d '{"text":"Article 5 introduces principles...","task":"summary"}'
```
**Unfavorable elements:**
```bash
curl -X POST http://localhost:8000/summarize -H "Content-Type: application/json" \
	-d '{"text":"This Agreement grants provider unilateral termination...","task":"unfavorable_elements"}'
```
**Conflicts analysis:**
```bash
curl -X POST http://localhost:8000/summarize -H "Content-Type: application/json" \
	-d '{"text":"Clause 4 says 3 years retention. Clause 12 says 7 years.","task":"conflicts"}'
```
**PDF upload:**
```bash
curl -X POST http://localhost:8000/summarize-pdf-stream -F "file=@sample.pdf" -F "task=conflicts" -F "focus=mutual exclusive terms"
```
**Batch fragments:**
```bash
curl -X POST http://localhost:8000/analyze-batch -H "Content-Type: application/json" \
	-d '{"task":"conflicts","fragments":["Section A ...","Section B ..."]}'
```

## Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```
Configure API base via `VITE_API_BASE` (defaults to http://localhost:8000).

**Features:**
- File upload (PDF)
- Text input
- Task selection (Summary/Unfavorable/Conflicts)
- Focus keyword input
- Streaming and non-streaming modes

## Environment
`.env` (backend):
```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
LLM_BACKEND=openai          # openai | ollama | basic
OLLAMA_MODEL=mistral        # used if LLM_BACKEND=ollama
ALLOW_BASIC_FALLBACK=1      # if 1, on quota errors falls back to heuristic summary
OPENAI_MAX_RETRIES=3
OPENAI_RETRY_BASE_DELAY=1.0
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
MAX_CHUNKS=30               # Limit chunks for rate limiting (comment out for full processing)
DEBUG_STREAM=1              # Enable debug logging
```
Frontend optional: `frontend/.env` → `VITE_API_BASE=http://localhost:8000`

## Tests
```bash
pytest -q
```

## Manual test idea
Use GDPR Articles 5–7 (principles, lawfulness, consent) to verify that the summary includes:
- lawful basis tracking
- right to withdraw consent  
- transparency obligations

## Example prompts
1. **Summary:** Summarize the following regulatory text into at most 3 clear sentences understandable to a banking officer.
2. **Unfavorable:** Identify potentially unfavorable or high-risk clauses for the contract signatory.
3. **Conflicts:** Find internally conflicting or inconsistent sections of the contract.

Corresponding task values: `summary`, `unfavorable_elements`, `conflicts`.

## Configuration
- `chunk_size` / `chunk_overlap`
- `task` selection
- optional `focus` keyword (adds extra direction)
- `MAX_CHUNKS` for rate limiting

## Disclaimer
Outputs are not legal advice. Verify with compliance / legal professionals.

## Potential extensions
- Retrieval (RAG) for question answering
- PDF / DOCX export of final report
- Risk severity scoring
- Local model support (Ollama / others)
- Progress tracking for large documents
- Resume processing on interruption

---
© 2025 Demo project. Made for regulatory compliance analysis.
