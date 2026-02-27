# ExamAI — Progress Report (27 February 2026)

---

## 1. Executive Summary

ExamAI is an AI-powered academic assistant that allows users to upload study materials and interact with the content via two distinct modes: a concise Q&A mode and a structured Teach mode. The system uses a RAG (Retrieval-Augmented Generation) pipeline built on FastAPI, FAISS, sentence-transformer embeddings, and a local LLM (FLAN-T5-base via HuggingFace Transformers).

**Current stage:** Functional prototype. All core features — file upload, RAG-based Q&A, Teach mode, multi-file processing, OCR, and topic extraction — are implemented and wired end-to-end. The frontend is a polished monochrome SPA communicating with the backend over REST. The system is demo-ready with known limitations documented below.

---

## 2. Technical Architecture Overview

### Backend Components

| Component | Implementation |
|-----------|---------------|
| Framework | FastAPI (single `main.py`, ~226 lines) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` via `HuggingFaceEmbeddings` |
| Vector Store | FAISS (in-memory, rebuilt on each upload) |
| LLM | `google/flan-t5-base` via `HuggingFacePipeline` (local, max 512 tokens) |
| RAG Chain | LangChain `RetrievalQA` with `stuff` chain type |
| Text Splitting | `RecursiveCharacterTextSplitter` (1000 chars, 200 overlap) |
| CORS | Open (`*` origins) |

### AI Pipeline Flow

```
User Upload → File Processor → Plain Text → Text Splitter → Embeddings → FAISS
User Question → FAISS Retriever → Context + Question → LLM (FLAN-T5) → Response
```

### Prompt Strategy

- **Q&A mode:** Uses default LangChain `RetrievalQA` prompt (no custom template).
- **Teach mode:** Custom `PromptTemplate` with 6 structured sections: Concept Overview, Key Definitions, Step-by-Step Explanation, Simple Example, Why This Matters, Practice Question. Includes anti-hallucination rules and markdown formatting instructions.

### Teach Mode Implementation

Teach mode is implemented by creating a separate `RetrievalQA` chain on each request with the teach prompt template injected via `chain_type_kwargs`. Both modes use the same retriever and LLM instance. The mode is selected via a `mode` parameter in the `/chat` request body (defaults to `"qa"` for backward compatibility).

---

## 3. Implemented Features

### Backend

- **Multi-file upload** (`POST /upload`): Accepts `List[UploadFile]` via multipart form. Supports `.pdf`, `.docx`, `.txt`, `.png`, `.jpg`, `.jpeg`.
- **File processing pipeline** (`utils/file_processor.py`):
  - PDF extraction via `PyPDFLoader`
  - DOCX extraction via `python-docx`
  - TXT extraction via UTF-8 file read
  - Image OCR via `pytesseract` + `Pillow`
  - Extension-based dispatcher function
- **Topic extraction** (`utils/topic_extractor.py`): Sends truncated text (20k char limit) to LLM with a JSON-array extraction prompt. Includes three-tier parsing: direct JSON, regex extraction, plain text fallback. Wrapped in try/except — never blocks upload.
- **Dual-mode chat** (`POST /chat`): Accepts `{ "question": str, "mode": "qa" | "teach" }`. Routes to default QA chain or teach chain based on mode.
- **Extension validation** with HTTP 400 errors for unsupported types.
- **Temp file cleanup** in both success and error paths.

### Frontend

- **Monochrome SPA** (HTML/CSS/JS, no frameworks): Inter font, matte black surfaces, charcoal panels, off-white text.
- **Multi-file drag-and-drop upload** with validation, animated progress bar, and document card display.
- **Q&A / Teach pill toggle** in chat header with active state styling.
- **Topic pill rendering**: Extracted topics displayed as pill-shaped tags in the document card.
- **Chat interface**: User/AI message bubbles with avatar icons, typing indicator, timestamp pills, auto-scroll.
- **Markdown rendering** for AI responses (`renderMarkdown`): Handles headings, bold, italic, inline code, lists, paragraphs.
- **Recent questions sidebar**: Clickable question history with relative timestamps.
- **New Session reset**: Clears all state (documents, topics, chat, mode, recent questions).
- **Client-side file validation** before upload.

---

## 4. Partially Implemented / In-Progress Features

| Feature | Status | Notes |
|---------|--------|-------|
| Topic extraction quality | Partial | Depends entirely on FLAN-T5-base's ability to produce JSON output. This small model often returns malformed or incomplete JSON. Fallback parsing mitigates but does not solve. |
| Teach mode structured output | Partial | The prompt requests 6 markdown sections, but FLAN-T5-base (512 max tokens) frequently truncates output mid-section. The structure works better with a larger LLM. |
| Markdown renderer | Basic | Handles `##`, `**`, `*`, `` ` ``, `-`, and numbered lists. Does not support triple-backtick code blocks, tables, or nested lists. Sufficient for current LLM output. |
| Error message display | Basic | Upload errors show server detail messages. Chat errors show generic "Something went wrong." text. No retry mechanism. |

---

## 5. System Capabilities

What the system can realistically do right now:

1. Accept one or more files (PDF, DOCX, TXT, images) via upload or drag-and-drop.
2. Extract text from all supported file types including OCR for images.
3. Build an in-memory FAISS vector index from the extracted content.
4. Attempt to extract and display syllabus topics from the uploaded content.
5. Answer questions about the uploaded content using RAG retrieval (Q&A mode).
6. Provide structured teaching responses with section-based formatting (Teach mode).
7. Render markdown-formatted responses in the chat UI.
8. Track recent questions for quick re-access.
9. Reset all state for a fresh session.

What the system **cannot** do:

- Persist data between server restarts (all state is in-memory).
- Handle multiple users simultaneously (single global `vector_store`).
- Process files asynchronously (upload blocks until complete).
- Retain chat history across sessions.
- Handle documents larger than FLAN-T5's effective context window.

---

## 6. Limitations & Technical Debt

### Critical

| Issue | Impact |
|-------|--------|
| **LLM is FLAN-T5-base (250M params, 512 max tokens)** | Severely limits response quality, length, and structured output capability. Teach mode sections are frequently truncated. Topic extraction often fails to produce valid JSON. |
| **No persistence** | FAISS index, chat history, and all state exist only in memory. Server restart = full data loss. |
| **Single-user architecture** | `vector_store` and `qa_chain` are global variables. Concurrent users would overwrite each other's data. |
| **CORS open to all origins** | Acceptable for hackathon but not production-safe. |

### Moderate

| Issue | Impact |
|-------|--------|
| **Teach chain recreated per request** | A new `RetrievalQA` chain is instantiated on every Teach mode request instead of being cached. Minor performance cost. |
| **No `requirements.txt`** | Dependencies are not tracked in a manifest file. The `venv` directory exists but there's no lockfile. |
| **`tempfile` import in `file_processor.py` is unused** | Dead import. Cosmetic. |
| **LangChain deprecation warning** | `langchain.document_loaders.PyPDFLoader` should be `langchain_community.document_loaders.PyPDFLoader`. Used in `file_processor.py`. |
| **Page/word estimates are heuristic** | File size-based estimation (size÷50 = pages) is inaccurate for images and DOCX files. |
| **OCR requires system-level Tesseract** | `pytesseract` is a wrapper; Tesseract must be installed separately (`brew install tesseract`). Not documented in project. |

### Minor

| Issue | Impact |
|-------|--------|
| `API_BASE` is hardcoded to `127.0.0.1:8000` | Frontend cannot be deployed separately without modification. |
| Upload icon SVG still says "PDF" | SVG text label in upload zone still reads "PDF" despite supporting multiple file types. |
| `chatEmpty` reference after `innerHTML` reset | New Session reconstructs the empty state element, but `chatEmpty` variable still points to the original (removed) element. Subsequent uploads after reset may fail to update the empty state text. |

---

## 7. Hackathon Readiness Assessment

### Stability: ⬛⬛⬛⬜⬜ (3/5)

The system is functional for a single-user demo. Core upload → chat flow works. The primary risk is the FLAN-T5-base model producing underwhelming or truncated responses, especially in Teach mode and topic extraction.

### Demo Impact: ⬛⬛⬛⬛⬜ (4/5)

The frontend is polished and premium-looking. The dual-mode toggle, topic pills, document card, and structured AI responses create a strong visual impression. The monochrome design system is cohesive and professional.

### Risk Areas

| Risk | Severity | Mitigation |
|------|----------|------------|
| FLAN-T5 produces short/poor responses | High | Switch to Gemini via `ChatGoogleGenerativeAI` for dramatically better output |
| Topic extraction returns empty array | Medium | Gracefully hidden in UI — no crash, just no pills shown |
| Large file causes slow upload | Medium | Text splitting and FAISS indexing are synchronous and blocking |
| OCR fails (Tesseract not installed) | Medium | Will raise 500 error — caught and surfaced to user |
| `chatEmpty` bug after New Session | Low | Only affects the empty-state text label; chat functionality unaffected |

### What Could Break During Demo

1. **Uploading a very large PDF** (>50 pages) — processing time could cause frontend timeout or perceived hang.
2. **Asking a complex question in Teach mode** — FLAN-T5 may produce a response that cuts off after 1-2 sections.
3. **Uploading an image without Tesseract installed** — will return a 500 error.
4. **Rapid successive uploads** — global state overwrite, no queuing.

---

## 8. Recommended Next Priorities

### High Impact

1. **Switch LLM to Gemini** (`ChatGoogleGenerativeAI`): This is the single highest-impact change. It would dramatically improve response quality for both Q&A and Teach modes, and make topic extraction reliable. The `llm` variable is used consistently, so the swap is localized to the initialization block in `main.py`.

2. **Generate `requirements.txt`**: Run `pip freeze > requirements.txt` in the venv. Critical for reproducibility and team deployment.

3. **Fix the `chatEmpty` reference bug**: Store the reference to `chatEmpty` after reconstruction in the New Session handler, or query the DOM fresh when needed.

### Medium Impact

4. **Fix the deprecated import** in `file_processor.py`: Change `from langchain.document_loaders import PyPDFLoader` to `from langchain_community.document_loaders import PyPDFLoader`.

5. **Cache the teach chain**: Build it once when `vector_store` is created rather than on every Teach mode request.

6. **Update upload icon**: Replace the "PDF" text in the upload zone SVG with a generic document icon since multiple file types are now supported.

### Nice-to-Have

7. **Add configurable `API_BASE`**: Read from environment or make it relative for easier deployment.

8. **Add loading skeleton for topic extraction**: Since topic extraction adds latency to upload, show a skeleton or spinner while topics load.

9. **Session-based state isolation**: Use a `session_id` pattern so multiple users don't overwrite each other's vector store.

---

*Report generated from direct codebase analysis on 27 February 2026.*
*Total codebase: 7 source files, ~1,750 lines of application code (excluding venv).*
