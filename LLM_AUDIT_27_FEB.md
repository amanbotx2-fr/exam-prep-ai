# ExamAI — LLM Audit (27 February 2026)

---

## 1. Current Active LLM

**Model:** `google/flan-t5-base` (250M parameters)
**Class:** `HuggingFacePipeline` (LangChain wrapper around HuggingFace Transformers)
**Max output tokens:** 512
**Execution:** Local CPU inference. No API calls. No cloud LLM.

**Gemini is NOT used anywhere in this codebase.** Despite project documentation referencing "Gemini via LangChain," no `ChatGoogleGenerativeAI`, no `langchain_google_genai`, and no Gemini API key are present in any file.

---

## 2. Where It Is Initialized

**File:** `backend/main.py`, lines 46–59

```python
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
```

This is the **only** LLM initialization in the entire codebase. There is exactly one `llm` variable, created once at module load.

---

## 3. Where It Is Used

The single `llm` instance is used in **all three execution paths**:

| Usage | File | Line(s) | Mechanism |
|-------|------|---------|-----------|
| **Q&A mode** | `main.py` | 136–138 | `RetrievalQA.from_chain_type(llm=llm, ...)` — built once during upload, stored as global `qa_chain` |
| **Teach mode** | `main.py` | 217–222 | `RetrievalQA.from_chain_type(llm=llm, ...)` — rebuilt on every Teach request with custom prompt |
| **Topic extraction** | `main.py` | 143 | `extract_topics(combined_text, llm)` — passed to `topic_extractor.py` which calls `llm.invoke(prompt)` |

All three paths use the exact same FLAN-T5-base instance. There is no secondary LLM.

---

## 4. Dead or Unused LLM Code

**None.** There are no unused LLM initializations, no commented-out Gemini imports, no stale API key references, and no alternative model configurations anywhere in the codebase.

The only imports related to LLM are:

```python
from langchain_community.llms import HuggingFacePipeline  # used
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline  # used
```

There is no `langchain_google_genai` import, no `ChatGoogleGenerativeAI` class, and no `GOOGLE_API_KEY` environment variable reference in any file.

---

## 5. Recommendation

### Verdict: Weak. Needs immediate replacement for hackathon demo.

| Aspect | Assessment |
|--------|-----------|
| **Q&A quality** | Poor. FLAN-T5-base produces short, often incomplete answers. Acceptable for trivial factual retrieval only. |
| **Teach mode** | Non-functional in practice. The prompt requests 6 structured markdown sections. FLAN-T5-base's 512-token cap means output is truncated after 1–2 sections at best. The teach prompt template is wasted. |
| **Topic extraction** | Unreliable. FLAN-T5-base rarely produces valid JSON arrays. The three-tier fallback parsing in `topic_extractor.py` exists specifically because this model cannot reliably follow output format instructions. |
| **Token limit** | 512 tokens max output is the hard ceiling set in the pipeline config. This is approximately 380 words — insufficient for any structured educational response. |

### Recommended Action

Replace the LLM initialization block (lines 42–59 of `main.py`) with:

```python
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=os.environ.get("GOOGLE_API_KEY"),
    temperature=0.3,
)
```

This is a **drop-in replacement**. The rest of the codebase (`RetrievalQA` chains, `extract_topics`, all prompts) will work without modification because they all reference the same `llm` variable and use the standard LangChain `.invoke()` / `.run()` interface.

**Impact of switch:**
- Teach mode 6-section output will actually be generated in full
- Topic extraction will reliably return JSON arrays
- Q&A responses will be substantially more coherent and detailed
- No other code changes required

**Requirements:**
- `pip install langchain-google-genai`
- Set `GOOGLE_API_KEY` environment variable
- Remove `transformers`, `torch` dependencies (optional, reduces install size)

---

*Audit based on direct inspection of `backend/main.py` (226 lines), `backend/utils/topic_extractor.py` (85 lines), and `backend/utils/file_processor.py` (62 lines). No other backend files exist.*
