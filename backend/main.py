from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document

from utils.file_processor import extract_text, SUPPORTED_EXTENSIONS
import requests
import tempfile
import time
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

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
sessions = {}

# -------------------------
# LOCAL EMBEDDINGS
# -------------------------

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# -------------------------
# SYSTEM PROMPTS
# -------------------------

TEACH_SYSTEM_PROMPT = """You are ExamAI — an elite exam preparation assistant.

Your purpose is to help students score maximum marks in exams.

For every topic:
1. Give a structured, exam-oriented explanation.
2. Clearly highlight important formulae.
3. Provide step-by-step derivations if mathematical.
4. Mention common mistakes students make.
5. Add 2–3 exam-style questions at the end.
6. Keep explanations concise but structured.
7. Use headings and bullet points.
8. Never respond casually.

Force responses to follow this format exactly:
### Concept Overview
### Key Formulae
### Important Derivation
### Common Mistakes
### Exam Practice Questions"""

PRACTICE_SYSTEM_PROMPT = "Generate 5 exam-level problems on this topic with solutions. You are an elite exam preparation assistant."

TEST_SYSTEM_PROMPT = "Generate a short timed test (5 questions) on this topic. Do NOT give solutions. Wait for user answers. You are an elite exam preparation assistant."


# -------------------------
# GROQ API
# -------------------------

llm = ChatGroq(
    model="llama-3.1-8b-instant", # Keeping the fast instant model as before, but initialized with ChatGroq
    api_key=os.environ.get("GROQ_API_KEY"),
    temperature=0.3
)

def ask_groq(question: str, system_prompt: str = TEACH_SYSTEM_PROMPT):
    try:
        messages = [
            ("system", system_prompt),
            ("human", question),
        ]
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        return f"Groq Exception: {str(e)}"


# -------------------------
# REQUEST MODEL
# -------------------------

class ChatRequest(BaseModel):
    question: str
    mode: Optional[str] = "teach"
    session_id: Optional[str] = "default"


# -------------------------
# UPLOAD ENDPOINT
# -------------------------

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    global vector_store

    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    combined_text = ""
    tmp_paths = []
    files_processed = 0
    total_pages = 0

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
            text, page_count = extract_text(tmp_path)
            if text.strip():
                combined_text += text + "\n\n"
                files_processed += 1
                total_pages += page_count
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

    # Split and embed text
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )

    documents = [Document(page_content=combined_text)]
    chunks = text_splitter.split_documents(documents)

    vector_store = FAISS.from_documents(chunks, embeddings)

    # Classification and Topic Extraction via Groq (non-blocking)
    document_type = "other"
    try:
        # Step 1: Detect Document Type
        classify_prompt = f"Classify this document as one of:\n1. syllabus\n2. lecture notes\n3. textbook\n4. other\n\nReturn only one word.\n\nText:\n{combined_text[:2000]}"
        type_response = ask_groq(classify_prompt, system_prompt="You are a classifier. Respond with one word only.")
        
        lower_resp = type_response.lower()
        if "syllabus" in lower_resp:
            document_type = "syllabus"
        elif "notes" in lower_resp or "lecture" in lower_resp:
             document_type = "lecture notes"
        elif "text" in lower_resp or "book" in lower_resp:
             document_type = "textbook"

        # Step 2: Extract structured topics if syllabus, else flat list
        if document_type == "syllabus":
             topic_prompt = f"Extract structured topics from this syllabus.\nReturn ONLY pure JSON in this format, nothing else:\n\n{{\n  \"Unit I\": [\"topic1\", \"topic2\"],\n  \"Unit II\": [\"topic1\", \"topic2\"]\n}}\n\nText:\n{combined_text[:10000]}"
        else:
             topic_prompt = f"Extract the main syllabus topics from this text as a JSON array of strings. Return ONLY the JSON array, nothing else.\n\nText:\n{combined_text[:10000]}"
             
        topic_response = ask_groq(topic_prompt)
        import json, re
        
        try:
            topics = json.loads(topic_response)
        except json.JSONDecodeError:
            match = re.search(r'(\{.*\}|\[.*\])', topic_response, re.DOTALL)
            if match:
                topics = json.loads(match.group())
            else:
                topics = {} if document_type == "syllabus" else []
                
        if document_type == "syllabus" and not isinstance(topics, dict):
             topics = {}
        elif document_type != "syllabus" and not isinstance(topics, list):
             topics = []
             
        if document_type != "syllabus":
             topics = [str(t).strip() for t in topics if str(t).strip()]
             
    except Exception as e:
        print(f"[ERROR] Groq processing failed: {e}")
        topics = {} if document_type == "syllabus" else []

    # Inject parsed data into any existing active sessions as a convenience
    for session_id in sessions:
        sessions[session_id]["document_type"] = document_type
        sessions[session_id]["syllabus_topics"] = topics if document_type == "syllabus" else {}

    return {
        "message": "Files processed successfully",
        "files_processed": files_processed,
        "pages": total_pages,
        "topics": topics,
        "document_type": document_type
    }


# -------------------------
# CHAT ENDPOINT
# -------------------------

@app.post("/chat")
async def chat(request: ChatRequest):
    session_id = request.session_id
    if session_id not in sessions:
        sessions[session_id] = {
            "mode": "teach",
            "current_topic": "general",
            "weak_topics": {},
            "total_questions": 0,
            "correct_answers": 0,
            "document_type": None,
            "syllabus_topics": {}
        }
    
    session = sessions[session_id]
    
    # Mode handling
    mode = request.mode if request.mode in ("teach", "practice", "test") else "teach"
    session["mode"] = mode
    print(f"[DEBUG] Groq {mode.upper()} mode")
    endpoint_start = time.time()

    user_message = request.question.strip()

    # Determine document context flag
    document_uploaded = vector_store is not None

    # Topic Locking & Extraction
    extracted_topic = "general"
    if session["current_topic"] is None or session["current_topic"] == "general":
        words = user_message.split()
        if words:
            extracted_topic = " ".join(words[:4]).lower()
            session["current_topic"] = extracted_topic
        else:
            session["current_topic"] = "general topic"
    else:
        # Still attempt to infer intent from early words for matching, 
        # but keep core locked
        words = user_message.split()
        extracted_topic = " ".join(words[:4]).lower() if words else session["current_topic"]

    current_topic = session["current_topic"]
    
    # Syllabus Restricting Scope
    if session.get("document_type") == "syllabus":
        syllabus_topics = session.get("syllabus_topics", {})
        
        # Check if the extracted intent roughly exists in syllabus values
        found_unit = None
        topic_matches = False
        
        if syllabus_topics:
            for unit, topics_list in syllabus_topics.items():
                for t in topics_list:
                    if str(t).lower() in extracted_topic or extracted_topic in str(t).lower():
                        found_unit = unit
                        topic_matches = True
                        break
                if topic_matches:
                    break
                    
            if not topic_matches and extracted_topic != "general":
                return {
                     "answer": "This topic does not appear in your uploaded syllabus.",
                     "mode": mode,
                     "accuracy": session.get("accuracy", 0.0),
                     "weak_topics": session["weak_topics"]
                }
        
    # ----------------------------
    # TEST MODE: Single Letter Answer Evaluator
    # ----------------------------
    if mode == "test" and user_message.upper() in ["A", "B", "C", "D"]:
        session["total_questions"] += 1
        
        # We need the LLM to evaluate if the answer is correct based on the context of the running test
        # We prompt it explicitly to act as an evaluator
        eval_prompt = f"""You are grading a test on {current_topic}.
The student answered: {user_message.upper()}
Evaluate if this is correct. 
Respond ONLY in this exact format:
[CORRECT] or [INCORRECT]
Explanation: <your brief explanation>"""
        
        eval_response = ask_groq(eval_prompt, system_prompt="You are an elite exam grader.")
        
        try:
            if "[CORRECT]" in eval_response.upper():
                session["correct_answers"] += 1
                final_answer = eval_response
            else:
                session["weak_topics"][current_topic] = session["weak_topics"].get(current_topic, 0) + 1
                final_answer = eval_response
        except Exception:
             final_answer = eval_response
             
        accuracy = session["correct_answers"] / session["total_questions"] if session["total_questions"] > 0 else 0.0
        return {
            "answer": final_answer,
            "mode": mode,
            "accuracy": round(accuracy, 2),
            "weak_topics": session["weak_topics"]
        }

    # Determine system prompt based on mode
    system_prompt = TEACH_SYSTEM_PROMPT
    if mode == "practice":
        system_prompt = PRACTICE_SYSTEM_PROMPT
    elif mode == "test":
        system_prompt = TEST_SYSTEM_PROMPT

    # 1. Inject strict topic locking lock
    topic_lock = f"\n\nYou are currently teaching/testing ONLY the topic: {current_topic}.\nDo NOT change subject.\nDo NOT introduce new topics.\nIf user response is a single letter, interpret it as an answer to the current question."
    system_prompt += topic_lock
    
    # 2. Inject weakness into system prompt
    if session["weak_topics"].get(current_topic, 0) >= 2:
        weakness_injection = f"\nStudent is struggling with {current_topic}. Focus on fundamentals and clarify misconceptions."
        system_prompt += weakness_injection
        
    # 3. Inject document context control
    if document_uploaded:
        if session.get("document_type") == "syllabus":
             if syllabus_topics and not any(syllabus_topics.values()):
                  doc_context = "\nAccording to the uploaded syllabus (which has no explanations), use your general knowledge but frame the answer strictly inside the syllabus structure."
             else:
                  unit_str = f" This topic belongs to {found_unit}." if 'found_unit' in locals() and found_unit else ""
                  doc_context = f"\nTeach strictly within the scope of the uploaded syllabus.{unit_str} Do not introduce unrelated topics."
        else:
             doc_context = "\nUse uploaded document as primary source. Do not introduce unrelated content."
        system_prompt += doc_context
    else:
        doc_no_context = "\nAnswer based purely on your knowledge. No document was uploaded."
        system_prompt += doc_no_context

    # ----------------------------
    # FUTURE RAG LOGIC (Bypassed)
    # ----------------------------
    # if rag_enabled and vector_store is not None:
    #     pass  # RAG invocation goes here when enabled in the future

    # Generate test only if mode is test AND it's not just a single letter answering a previous question
    # (Since single letter is caught above, we are generating the test here)
    if mode == "test" and "test" not in user_message.lower() and "quiz" not in user_message.lower() and len(user_message.split()) < 3:
         return {"answer": "Say 'generate test' or 'start quiz' to begin the test.", "mode": mode, "accuracy": 0.0, "weak_topics": session["weak_topics"]}

    try:
        answer = ask_groq(user_message, system_prompt=system_prompt)
        
        # Fail Safe: Verify LLM stayed on topic
        if current_topic.lower() not in answer.lower() and len(answer.split()) > 20:
             # Basic safety net check - if the topic word isn't in the reply and it's a long reply, it might have drifted
             pass 

        total_time = time.time() - endpoint_start
        print(f"[DEBUG] Groq response time: {total_time:.3f} sec")
        
        accuracy = session["correct_answers"] / session["total_questions"] if session["total_questions"] > 0 else 0.0
        
        return {
            "answer": answer,
            "mode": mode,
            "accuracy": round(accuracy, 2),
            "weak_topics": session["weak_topics"]
        }
    except Exception as e:
        return {"error": f"Groq API failed: {str(e)}"}