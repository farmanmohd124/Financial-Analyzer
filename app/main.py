"""
Financial Document Analyzer — FastAPI entrypoint.

Day 1-2 goal: get a document in via upload, extract text, and run one
LLM extraction call end-to-end. Everything else (queue, DB, caching)
gets layered on top of this once the core loop works.
"""

import os
import uuid
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.parsing import extract_text_from_pdf, has_financial_statement_sections, split_into_sections
from app.extraction import classify_sections_with_llm, extract_key_metrics
from app.database import DocumentDatabase
from app.storage import store_pdf

app = FastAPI(title="Financial Document Analyzer", version="0.1.0")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

database = DocumentDatabase(os.getenv("DATABASE_PATH", "./filingscope.db"))


@app.on_event("startup")
def initialize_database():
    database.initialize()


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


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
    contents = await file.read()
    database.save_document(document_id, file.filename, "processing")

    try:
        store_pdf(document_id, contents)
        text = extract_text_from_pdf(BytesIO(contents))
        parsed_sections = split_into_sections(text)
        if has_financial_statement_sections(parsed_sections):
            print("Skipping section classification; financial statement sections were parsed")
            classified_sections = {}
        else:
            classified_sections = classify_sections_with_llm(text)
        # Keep parser-native financial sections for metric extraction and add
        # classifier sections for documents with unusual headings.
        sections = {**parsed_sections, **classified_sections}
        result = extract_key_metrics(sections)

        database.save_document(document_id, file.filename, "complete", result=result)
    except Exception as e:
        database.save_document(document_id, file.filename, "failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    return JSONResponse(database.get_document(document_id))


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
    temp_path = Path("uploads") / f"debug_{uuid.uuid4()}_{Path(file.filename).name}"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
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
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.get("/documents")
def list_documents():
    return database.list_documents()
