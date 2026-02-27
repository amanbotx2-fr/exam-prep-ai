from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import HuggingFacePipeline
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.schema import Document

from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
from utils.file_processor import extract_text, SUPPORTED_EXTENSIONS
from utils.topic_extractor import extract_topics
import tempfile
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# GLOBAL VARIABLES
# -------------------------

vector_store = None
qa_chain = None

# -------------------------
# LOCAL EMBEDDINGS
# -------------------------

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# -------------------------
# LOCAL LLM (FLAN-T5)
# -------------------------

model_name = "google/flan-t5-base"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

pipe = pipeline(
    "text2text-generation",
    model=model,
    tokenizer=tokenizer,
    max_length=512,
)

llm = HuggingFacePipeline(pipeline=pipe)


# -------------------------
# REQUEST MODEL
# -------------------------

class ChatRequest(BaseModel):
    question: str
    mode: Optional[str] = "qa"


# -------------------------
# UPLOAD ENDPOINT
# -------------------------

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    global vector_store, qa_chain

    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    combined_text = ""
    tmp_paths = []
    files_processed = 0

    for file in files:
        # Validate extension
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
            )

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
            tmp_paths.append(tmp_path)

        # Extract text
        try:
            text = extract_text(tmp_path)
            if text.strip():
                combined_text += text + "\n\n"
                files_processed += 1
        except Exception as e:
            # Clean up on error
            for p in tmp_paths:
                if os.path.exists(p):
                    os.remove(p)
            raise HTTPException(
                status_code=500,
                detail=f"Error processing {file.filename}: {str(e)}",
            )

    # Clean up temp files
    for p in tmp_paths:
        if os.path.exists(p):
            os.remove(p)

    if not combined_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the uploaded files.")

    # Reuse existing pipeline: split → embed → FAISS
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )

    documents = [Document(page_content=combined_text)]
    chunks = text_splitter.split_documents(documents)

    vector_store = FAISS.from_documents(chunks, embeddings)

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=vector_store.as_retriever(),
    )

    # Extract syllabus topics via LLM (non-blocking on failure)
    try:
        topics = extract_topics(combined_text, llm)
    except Exception:
        topics = []

    return {
        "message": "Files processed successfully",
        "files_processed": files_processed,
        "topics": topics,
    }


# -------------------------
# TEACH MODE PROMPT
# -------------------------

TEACH_PROMPT_TEMPLATE = """You are an academic tutor helping a student understand their syllabus.

Using ONLY the provided document context:

Teach the concept clearly and structurally.

Context:
{context}

Question: {question}

Structure your response exactly like this:

## Concept Overview
(2–3 clear sentences)

## Key Definitions
- Term 1:
- Term 2:

## Step-by-Step Explanation
(Numbered explanation if applicable)

## Simple Example
(A short illustrative example)

## Why This Matters
(Explain how this fits into the syllabus or course)

## Practice Question
(End with one short question for the student)

Rules:
- Do NOT hallucinate outside the provided context
- Do NOT become overly verbose
- Stay grounded in document chunks
- Keep formatting clean (Markdown compatible)
"""

teach_prompt = PromptTemplate(
    template=TEACH_PROMPT_TEMPLATE,
    input_variables=["context", "question"],
)


# -------------------------
# CHAT ENDPOINT
# -------------------------

@app.post("/chat")
async def chat(request: ChatRequest):
    global qa_chain, vector_store

    if qa_chain is None or vector_store is None:
        return {"error": "Upload a PDF first."}

    mode = request.mode if request.mode in ("qa", "teach") else "qa"

    if mode == "teach":
        teach_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=vector_store.as_retriever(),
            chain_type_kwargs={"prompt": teach_prompt},
        )
        result = teach_chain.run(request.question)
    else:
        result = qa_chain.run(request.question)

    return {"answer": result}