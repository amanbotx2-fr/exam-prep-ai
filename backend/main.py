import os
import uuid
import json
import tempfile
import re
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import docx
import fitz  # PyMuPDF
from langchain_groq import ChatGroq
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = ChatGroq(
    model="llama-3.1-8b-instant",
    api_key=os.environ.get("GROQ_API_KEY"),
    temperature=0.3
)

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

sessions = {}

def get_session(session_id: str):
    if session_id not in sessions:
        sessions[session_id] = {
            "mode": "teach",
            "test_active": False,
            "questions": [],
            "current_q": 0,
            "score": 0,
            "weak_topics": {},
            "vectorstore": None,
            "topic": "general"
        }
    return sessions[session_id]

class ChatRequest(BaseModel):
    message: str
    mode: str
    session_id: str

def call_llm(prompt_messages):
    print(f"[DEBUG] Groq CALL")
    response = llm.invoke(prompt_messages)
    return response.content

def validate_mcq_structure(questions: list) -> bool:
    if not isinstance(questions, list) or len(questions) != 5:
        return False
    for q in questions:
        if not isinstance(q, dict):
            return False
        if "question" not in q or "options" not in q or "correct" not in q:
            return False
        if not isinstance(q["options"], dict):
            return False
        if str(q["correct"]).lower() not in ["a", "b", "c", "d"]:
            return False
    return True

def validate_mcq_relevance(questions: list, topic: str) -> bool:
    topic_keywords = [w.lower() for w in topic.split() if len(w) > 2]
    if not topic_keywords:
        return True
    all_text = ""
    for q in questions:
        all_text += q["question"] + " " + " ".join(q["options"].values()) + " "
    all_text = all_text.lower()
    matches = sum(1 for kw in topic_keywords if kw in all_text)
    ratio = matches / len(topic_keywords)
    if ratio < 0.3:
        print(f"[TOPIC DRIFT] Only {matches}/{len(topic_keywords)} topic keywords found across all questions")
        return False
    return True

def generate_mcqs(topic: str, context: str) -> list:
    sys_prompt = (
        f"You are a strict academic exam question generator.\n"
        f"You MUST generate exactly 5 multiple-choice questions ONLY about: {topic}\n"
        f"Every question MUST directly test conceptual or numerical understanding of {topic}.\n"
        f"Do NOT generate questions about any other subject.\n"
        f"Do NOT include explanations, markdown, or any text outside the JSON.\n"
        f"Return ONLY a pure JSON array.\n"
        f"Format:\n"
        f'[{{"question":"...","options":{{"a":"...","b":"...","c":"...","d":"..."}},"correct":"a"}}]\n'
    )
    human_prompt = (
        f"Generate 5 MCQs strictly about: {topic}\n"
    )
    if context:
        human_prompt += f"Use this context as source material:\n{context}\n"

    best_result = []

    for attempt in range(3):
        print(f"[DEBUG] MCQ generation attempt {attempt + 1} for topic: {topic}")
        content = call_llm([("system", sys_prompt), ("human", human_prompt)])
        try:
            match = re.search(r'\[.*\]', content, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else json.loads(content)
            if validate_mcq_structure(parsed):
                best_result = parsed
                if validate_mcq_relevance(parsed, topic):
                    print(f"[DEBUG] MCQ generation succeeded on attempt {attempt + 1}")
                    return parsed
                else:
                    print(f"[WARN] MCQ relevance check failed on attempt {attempt + 1}, retrying...")
            else:
                print(f"[WARN] MCQ structure invalid on attempt {attempt + 1}, retrying...")
        except Exception as e:
            print(f"[ERROR] MCQ parse failed on attempt {attempt + 1}: {e}")

    if best_result:
        print(f"[WARN] Returning best-effort MCQs for topic: {topic}")
        return best_result

    print(f"[ERROR] All MCQ generation attempts failed for topic: {topic}")
    return []

@app.post("/new-session")
def create_session():
    new_id = str(uuid.uuid4())
    sessions[new_id] = {
        "mode": "teach",
        "test_active": False,
        "questions": [],
        "current_q": 0,
        "score": 0,
        "weak_topics": {},
        "vectorstore": None,
        "topic": "general"
    }
    return {"session_id": new_id}

@app.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    session_id: str = Form(...)
):
    session = get_session(session_id)
    combined_text = ""
    
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext == ".docx":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(await file.read())
                tmp_path = tmp.name
            try:
                doc = docx.Document(tmp_path)
                text = "\n".join([para.text for para in doc.paragraphs])
                combined_text += text + "\n\n"
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    
        elif ext == ".pdf":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(await file.read())
                tmp_path = tmp.name
            try:
                doc = fitz.open(tmp_path)
                text = ""
                for page in doc:
                    text += page.get_text() + "\n"
                combined_text += text + "\n\n"
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        else:
            try:
                content = await file.read()
                combined_text += content.decode("utf-8", errors="ignore") + "\n\n"
            except Exception:
                pass

    if not combined_text.strip():
        raise HTTPException(status_code=400, detail="No readable text available.")
        
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    chunks = splitter.split_text(combined_text)
    
    if chunks:
        vectorstore = FAISS.from_texts(chunks, embeddings)
        session["vectorstore"] = vectorstore

    return {"message": "Document processed and semantically indexed."}

@app.post("/chat")
async def chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    print(f"[DEBUG] RAW REQUEST BODY: {body}")
        
    # Safely extract fields
    user_message = body.get("message") or body.get("text") or body.get("user_input") or ""
    mode = body.get("mode") or body.get("currentMode") or "teach"
    req_session_id = body.get("session_id") or body.get("sessionId")
    
    if not user_message:
        return {"error": "Message is required"}
        
    if not req_session_id:
        req_session_id = str(uuid.uuid4())
        
    session = get_session(req_session_id)
    user_message = user_message.strip()
    
    if session["topic"] == "general" and len(user_message.split()) > 0:
        session["topic"] = user_message[:100]

    current_topic = session["topic"]

    if mode == "test":
        if not session["test_active"]:
            session["mode"] = "test"
            session["test_active"] = True
            
            context_str = ""
            if session["vectorstore"]:
                docs = session["vectorstore"].similarity_search(current_topic, k=3)
                context_str = "\n".join(d.page_content for d in docs)
                
            questions = generate_mcqs(current_topic, context_str)
            if not questions:
                session["test_active"] = False
                session["mode"] = "teach"
                return {
                    "answer": "Failed to generate test. Returning to teach mode.",
                    "mode": "teach",
                }
            
            session["questions"] = questions
            session["current_q"] = 0
            session["score"] = 0
            
            q = questions[0]
            q_text = f"**Test Started for {current_topic}**\n\nQuestion 1:\n{q['question']}\n\nA) {q['options'].get('a','')}\nB) {q['options'].get('b','')}\nC) {q['options'].get('c','')}\nD) {q['options'].get('d','')}"
            
            return {
                "answer": q_text,
                "mode": "test"
            }
        else:
            user_ans = user_message.lower()
            if len(user_ans) > 1 or user_ans not in ["a", "b", "c", "d"]:
                return {
                    "answer": "You are currently in Test mode. Please answer with a, b, c, or d.",
                    "mode": "test"
                }

            idx = session["current_q"]
            q = session["questions"][idx]
            correct_ans = str(q.get("correct", "a")).lower()
            
            status = "correct" if user_ans == correct_ans else "incorrect"

            if status == "correct":
                session["score"] += 1
                feedback = f"**Correct!** The answer is {correct_ans.upper()}.\n\n"
            else:
                session["weak_topics"][current_topic] = session["weak_topics"].get(current_topic, 0) + 1
                feedback = f"**Incorrect.** The correct answer is {correct_ans.upper()}.\n\n"
                
            session["current_q"] += 1
            
            if session["current_q"] >= len(session["questions"]):
                total = len(session["questions"])
                score = session["score"]
                session["mode"] = "teach"
                session["test_active"] = False
                session["questions"] = []
                session["current_q"] = 0
                return {
                    "status": status,
                    "answer": feedback + f"**Test Completed!**\nYour score: {score}/{total}\nReturning to teach mode.",
                    "mode": "teach"
                }
            else:
                next_idx = session["current_q"]
                next_q = session["questions"][next_idx]
                q_text = f"Question {next_idx + 1}:\n{next_q['question']}\n\nA) {next_q['options'].get('a','')}\nB) {next_q['options'].get('b','')}\nC) {next_q['options'].get('c','')}\nD) {next_q['options'].get('d','')}"
                return {
                    "status": status,
                    "next_question": f"Question {next_idx + 1}",
                    "answer": feedback + q_text,
                    "mode": "test"
                }

    elif mode in ["teach", "practice"]:
        session["mode"] = mode
        session["test_active"] = False
        
        context_str = ""
        if session["vectorstore"]:
            docs = session["vectorstore"].similarity_search(user_message, k=3)
            context_str = "\n".join(d.page_content for d in docs)
            
        sys_prompt = f"Current Mode: {mode.upper()}\nCurrent Topic: {current_topic}\n"
        sys_prompt += "Instruction: You are ExamAI, a strict and intelligent backend. You cannot change the topic or mode. If in test mode, you must not generate new content or evaluate MCQs.\n"
        
        if context_str:
            sys_prompt += f"Use ONLY the provided context from uploaded document.\n<context>\n{context_str}\n</context>\n"
            
        if session["weak_topics"].get(current_topic, 0) >= 2:
            sys_prompt += "Student has shown weakness in this topic. Reinforce fundamentals clearly.\n"
            
        if mode == "teach":
            sys_prompt += "Teach the subject carefully. Use markdown headers, bolding, and bullet points."
        elif mode == "practice":
            sys_prompt += "Generate 5 practice problems (not a test) with step-by-step solutions formatted clearly in markdown."
            
        try:
            answer = call_llm([("system", sys_prompt), ("human", user_message)])
        except Exception as e:
            answer = f"Error communicating with LLM: {str(e)}"
            
        return {
            "answer": answer,
            "mode": session["mode"]
        }
    
    return {"answer": "Invalid mode specified.", "mode": mode}