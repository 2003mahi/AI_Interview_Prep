import re
from typing import List, Tuple
import os
import openai
from ..config import settings

# Simple character-based chunker (you can replace with token‑based splitter later)
def chunk_text(text: str, max_chars: int = 1000) -> List[str]:
    """Split *text* into chunks of at most *max_chars* characters.
    The function tries to split on paragraph boundaries first.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                chunks.append(current)
            # If a single paragraph exceeds max_chars, split it brutally
            while len(para) > max_chars:
                chunks.append(para[:max_chars])
                para = para[max_chars:]
            current = para
    if current:
        chunks.append(current)
    return chunks

def embed_text(text: str) -> List[float]:
    """Return OpenAI ada‑002 embedding for *text*.
    In production you would cache embeddings; here we call the API directly.
    """
    openai.api_key = settings.OPENAI_API_KEY
    rsp = openai.Embedding.create(model="text-embedding-ada-002", input=text)
    return rsp["data"][0]["embedding"]

# Prompt-injection defense – comprehensive regex filters
_REJECT_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
    r"disregard\s+(?:the\s+)?(?:system\s+prompt|rules|rubric|criteria)",
    r"you\s+are\s+now\s+(?:an?\s+)?(?:unrestricted|dan|jailbreak)",
    r"system\s+(?:prompt|override|message)",
    r"bypass\s+(?:safety|guardrails|filters)",
    r"<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]",
    r"forget\s+(?:all\s+)?(?:previous|prior)\s+(?:context|instructions)",
    r"reveal\s+(?:the\s+)?(?:system\s+prompt|hidden\s+instructions)",
    r"you\s+are\s+not\s+required\s+to\s+follow",
]

def is_safe_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    for pat in _REJECT_PATTERNS:
        if re.search(pat, lowered):
            return False
    return True

# Helper to format citations
def format_citations(docs: List[Tuple[int, str]]) -> str:
    """Given a list of (doc_id, chunk_index) pairs, return a markdown citation string.
    Example: "Sources: [doc‑1#c0], [doc‑2#c3]"
    """
    parts = [f"[{doc_id}#c{chunk}]" for doc_id, chunk in docs]
    return "Sources: " + ", ".join(parts)
