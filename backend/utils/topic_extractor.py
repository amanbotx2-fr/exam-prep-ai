"""
ExamAI — Topic Extractor
Extracts structured syllabus topics from document text using LLM.
"""

import json
import re
from typing import List


# Max characters to send to the LLM to avoid token overflow
MAX_TEXT_LENGTH = 20000

TOPIC_EXTRACTION_PROMPT = """Extract a clean list of syllabus topics from this academic content.
Return ONLY a JSON array of topic strings.
No explanations.
No markdown.
No extra text.

Content:
{text}
"""


def extract_topics(text: str, llm) -> List[str]:
    """
    Send truncated text to the LLM and extract a list of topic strings.
    Returns an empty list on any parsing failure.
    """
    if not text or not text.strip():
        return []

    # Truncate to avoid token overflow
    truncated = text[:MAX_TEXT_LENGTH]

    prompt = TOPIC_EXTRACTION_PROMPT.format(text=truncated)

    try:
        # Works with both HuggingFacePipeline and ChatGoogleGenerativeAI
        result = llm.invoke(prompt)

        # Handle AIMessage or plain string
        if hasattr(result, "content"):
            raw = result.content
        else:
            raw = str(result)

        raw = raw.strip()

        # Try direct JSON parse first
        topics = json.loads(raw)
        if isinstance(topics, list):
            return [str(t).strip() for t in topics if str(t).strip()]

        # If it's a dict with a key containing the list
        if isinstance(topics, dict):
            for v in topics.values():
                if isinstance(v, list):
                    return [str(t).strip() for t in v if str(t).strip()]

        return []

    except json.JSONDecodeError:
        # Attempt to extract JSON array from mixed output
        try:
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                topics = json.loads(match.group())
                if isinstance(topics, list):
                    return [str(t).strip() for t in topics if str(t).strip()]
        except Exception:
            pass

        # Fallback: split by newlines/dashes if LLM returned plain text list
        lines = raw.replace("- ", "\n").split("\n")
        topics = [
            line.strip().strip("-•*").strip().strip('"').strip("'")
            for line in lines
            if line.strip() and len(line.strip()) > 2
        ]
        return topics[:30] if topics else []

    except Exception:
        return []
