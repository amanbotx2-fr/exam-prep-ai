<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Groq-LLaMA_3.1-FF6F00?style=for-the-badge" />
  <img src="https://img.shields.io/badge/FAISS-Semantic_Search-4285F4?style=for-the-badge" />
  <img src="https://img.shields.io/badge/HuggingFace-Embeddings-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" />
  <img src="https://img.shields.io/badge/Vanilla_JS-Frontend-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black" />
</p>

# 🎓 ExamAI — AI-Powered Exam Preparation System

> **An intelligent, session-aware study assistant that teaches, generates practice problems, and conducts MCQ tests — all powered by RAG and LLM, with strict backend-controlled state.**

ExamAI is not a chatbot. It is a **deterministic exam engine** where the backend controls every aspect of the learning flow: mode transitions, topic locking, question generation, answer evaluation, score tracking, and adaptive reinforcement — the LLM never touches system state.

---

## 🏗️ Architecture

```
exam-ai/
├── backend/
│   └── main.py              # FastAPI server — session engine, RAG, MCQ, LLM
├── frontend/
│   ├── index.html            # UI shell — upload zone, chat, mode toggle
│   ├── style.css             # Dark theme, glassmorphism, responsive layout
│   └── script.js             # Session management, fetch logic, rendering
├── .env                      # GROQ_API_KEY (not committed)
├── .gitignore
├── requirements.txt
└── README.md
```

### System Flow

```
┌──────────────┐     POST /new-session      ┌──────────────────┐
│   Frontend   │ ─────────────────────────▶  │   FastAPI Server  │
│  (Vanilla JS)│                             │                  │
│              │     POST /upload            │  Session Store   │
│  file input  │ ─────────────────────────▶  │  ┌────────────┐  │
│              │     (PDF/DOCX → FAISS)      │  │ session_id  │  │
│              │                             │  │ mode        │  │
│  chat input  │     POST /chat              │  │ topic       │  │
│  + mode      │ ─────────────────────────▶  │  │ questions[] │  │
│  + session_id│     {message, mode, sid}    │  │ score       │  │
│              │                             │  │ vectorstore │  │
│              │  ◀───────────────────────   │  │ weak_topics │  │
│  render with │     {answer, mode}          │  └────────────┘  │
│  marked.js + │                             │                  │
│  KaTeX       │                             │  Groq LLaMA 3.1  │
└──────────────┘                             └──────────────────┘
```

---

## ✨ Features

### 📖 Teach Mode
- Ask any topic → get structured, exam-oriented explanations
- Markdown headings, bold, bullet points, LaTeX math
- If a document is uploaded, answers are grounded in the document via RAG (top-3 semantic chunks)

### ✏️ Practice Mode
- Generates 5 practice problems with step-by-step solutions
- Uses uploaded document context when available

### 📝 Test Mode (Backend-Controlled MCQ Engine)
- Generates 5 MCQs via LLM, locked to the current topic
- Questions stored server-side with correct answers
- Only accepts `a`, `b`, `c`, `d` — any other input is rejected
- **Evaluation is 100% backend** — LLM is never called during answer checking
- Tracks score, provides per-question feedback
- Weak topics auto-tracked for adaptive reinforcement

### 📄 Document Upload (RAG Pipeline)
- Supports **PDF** (PyMuPDF) and **DOCX** (python-docx)
- Text is chunked (800 tokens, 150 overlap) and embedded with `all-MiniLM-L6-v2`
- Stored as a **FAISS** vectorstore, scoped to the session
- Retrieved chunks injected into LLM prompts as grounded context

### 🧠 Adaptive Memory
- Weak topics accumulate across test attempts
- When `weak_topics[topic] >= 2`, the system prompt is augmented:
  *"Student has shown weakness in this topic. Reinforce fundamentals clearly."*

### 🔒 Session Isolation
- Each session has its own state, vectorstore, and score
- No cross-session data leakage
- `/new-session` creates a clean slate with a new UUID
- Frontend persists `session_id` in `localStorage`

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- [Groq API Key](https://console.groq.com/) (free tier available)

### 1. Clone & Setup

```bash
git clone https://github.com/amanbotx2-fr/exam-prep-ai.git
cd exam-prep-ai
```

### 2. Backend Setup

```bash
cd backend
python3 -m venv ../venv
source ../venv/bin/activate
pip install -r ../requirements.txt
```

### 3. Configure Environment

Create `.env` in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
```

### 4. Start Backend

```bash
cd backend
uvicorn main:app --reload
```

Server runs at `http://127.0.0.1:8000`

### 5. Start Frontend

```bash
cd frontend
python3 -m http.server 5500
```

Open `http://localhost:5500` in your browser.

---

## 🧪 Demo Flow

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open app | Session auto-created via `/new-session` |
| 2 | Type "Explain Fourier Series" | Structured markdown explanation with math |
| 3 | Upload a PDF syllabus | Document chunked, embedded, indexed in FAISS |
| 4 | Ask "What is a Fourier coefficient?" | Answer grounded in uploaded document |
| 5 | Switch to **Test** mode | 5 MCQs generated, locked to current topic |
| 6 | Answer "b" | Backend evaluates, shows correct/incorrect |
| 7 | Complete all 5 | Score displayed, auto-returns to Teach mode |
| 8 | Ask same topic again | System reinforces weak areas if score was low |

---

## 🔧 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **LLM** | Groq (LLaMA 3.1 8B) | Teaching, practice generation, MCQ generation |
| **Embeddings** | `all-MiniLM-L6-v2` | Sentence-level semantic embeddings |
| **Vector Store** | FAISS | In-memory similarity search |
| **Backend** | FastAPI | REST API, session management, mode routing |
| **PDF Parsing** | PyMuPDF (fitz) | Extract text from PDF documents |
| **DOCX Parsing** | python-docx | Extract text from Word documents |
| **Frontend** | Vanilla HTML/CSS/JS | Zero-framework, lightweight UI |
| **Markdown** | marked.js + DOMPurify | Safe HTML rendering of LLM output |
| **Math** | KaTeX | LaTeX formula rendering |

---

## 📁 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/new-session` | Create new session, returns `{session_id}` |
| `POST` | `/upload` | Upload PDF/DOCX, build FAISS vectorstore |
| `POST` | `/chat` | Send message + mode + session_id, get response |

### `/chat` Request Body

```json
{
  "message": "Explain integration by parts",
  "mode": "teach",
  "session_id": "uuid-string"
}
```

### `/chat` Response

```json
{
  "answer": "## Integration by Parts\n...",
  "mode": "teach"
}
```

---

## 🛡️ Security

- **No hardcoded API keys** — all secrets loaded via `python-dotenv`
- `.env` is in `.gitignore`
- LLM output sanitized with **DOMPurify** before rendering
- Backend is the single source of truth — frontend cannot modify session state

---

## 🔮 Future Improvements

- [ ] Persistent session storage (Redis / SQLite)
- [ ] Multi-user authentication
- [ ] Spaced repetition scheduling based on weak topics
- [ ] Export test results as PDF report
- [ ] Support for image-based questions (OCR)
- [ ] Deployment on Render / Railway with production ASGI server
- [ ] WebSocket streaming for real-time LLM responses

---

## 🏷️ Repository Tags

`ai` `exam-preparation` `fastapi` `rag` `faiss` `groq` `llama` `mcq-generator` `study-assistant` `langchain` `hackathon` `education` `nlp`
