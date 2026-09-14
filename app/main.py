"""
Financial Document Analyzer — FastAPI entrypoint.

Day 1-2 goal: get a document in via upload, extract text, and run one
LLM extraction call end-to-end. Everything else (queue, DB, caching)
gets layered on top of this once the core loop works.
"""

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

load_dotenv()

from app.parsing import extract_text_from_pdf, split_into_sections
from app.extraction import extract_key_metrics

app = FastAPI(title="Financial Document Analyzer", version="0.1.0")

# Local storage for now — swap for S3 once the core pipeline works (see README)
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory store for now — swap for Postgres once you add persistence
DOCUMENTS: dict[str, dict] = {}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    """
    Upload a 10-K / earnings call PDF. Returns a document_id you can
    use to check status and fetch results.

    NOTE: this is synchronous for now (v1). Once this works end-to-end,
    swap the processing call for an SQS message + background worker
    so uploads return instantly instead of blocking on LLM calls.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported right now")

    document_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{document_id}.pdf"

    contents = await file.read()
    file_path.write_bytes(contents)

    DOCUMENTS[document_id] = {
        "id": document_id,
        "filename": file.filename,
        "status": "processing",
        "result": None,
    }

    try:
        text = extract_text_from_pdf(str(file_path))
        sections = split_into_sections(text)
        result = extract_key_metrics(sections)

        DOCUMENTS[document_id]["status"] = "complete"
        DOCUMENTS[document_id]["result"] = result
    except Exception as e:
        DOCUMENTS[document_id]["status"] = "failed"
        DOCUMENTS[document_id]["error"] = str(e)
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    return JSONResponse(DOCUMENTS[document_id])


@app.post("/debug/parse")
async def debug_parse(file: UploadFile = File(...)):
    """
    Temporary debug endpoint: upload a PDF and see exactly what
    sections were extracted and their lengths, without running
    the LLM extraction. Use this to diagnose why metrics extraction
    is missing data.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported right now")

    contents = await file.read()
    temp_path = UPLOAD_DIR / f"debug_{uuid.uuid4()}_{file.filename}"
    temp_path.write_bytes(contents)

    text = extract_text_from_pdf(str(temp_path))
    sections = split_into_sections(text)

    return {
        "total_text_length": len(text),
        "sections_found": {k: len(v) for k, v in sections.items()},
        "first_500_chars_of_each_section": {k: v[:500] for k, v in sections.items()},
    }


@app.get("/documents/{document_id}")
def get_document(document_id: str):
    doc = DOCUMENTS.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.get("/documents")
def list_documents():
    return list(DOCUMENTS.values())
