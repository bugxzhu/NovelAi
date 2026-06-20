"""Chunk Markdown chapter content into retrieval-ready pieces.

Pure functions. No LLM calls, no DB I/O.
"""
import re
from dataclasses import dataclass

MAX_PARAGRAPH_CHARS = 800
# Paragraphs longer than this get split on sentence boundaries even if they
# would still fit under MAX_PARAGRAPH_CHARS, so retrieval chunks stay focused.
SOFT_SPLIT_CHARS = 500

_DESCRIPTION_MARKERS = (
    "看", "看见", "看到", "闻", "听见", "听到",
    "摸", "触摸", "走", "跑", "坐", "站",
)


@dataclass
class Chunk:
    text: str
    chunk_type: str  # 'paragraph' | 'dialogue' | 'description'
    char_count: int


def chunk_markdown(content: str) -> list[Chunk]:
    """Split Markdown content into chunks.

    Strategy:
    1. Split by double-newline (Markdown paragraph boundaries).
    2. Skip whitespace-only paragraphs.
    3. Paragraphs > SOFT_SPLIT_CHARS: re-split on sentence terminators so
       chunks stay focused; any chunk stays <= MAX_PARAGRAPH_CHARS.
    4. Classify chunk_type by simple heuristics.
    """
    if not content or not content.strip():
        return []
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    for para in paragraphs:
        if len(para) <= SOFT_SPLIT_CHARS:
            chunks.append(_classify(para))
        else:
            for piece in _split_long_paragraph(para):
                chunks.append(_classify(piece))
    return chunks


def _split_long_paragraph(text: str) -> list[str]:
    """Split a long paragraph into focused pieces.

    Splits by sentence terminators (。！？.!?), accumulates sentences until
    adding the next would exceed SOFT_SPLIT_CHARS, then starts a new piece.
    Any single sentence longer than MAX_PARAGRAPH_CHARS is hard-split on
    character boundaries so the size invariant always holds.
    """
    sentences = _split_sentences(text)
    pieces: list[str] = []
    buffer = ""
    for sent in sentences:
        # Hard-split sentences that exceed the hard limit on their own.
        if len(sent) > MAX_PARAGRAPH_CHARS:
            if buffer:
                pieces.append(buffer)
                buffer = ""
            for hard in _hard_split(sent):
                pieces.append(hard)
            continue
        if len(buffer) + len(sent) > SOFT_SPLIT_CHARS and buffer:
            pieces.append(buffer)
            buffer = sent
        else:
            buffer += sent
    if buffer:
        pieces.append(buffer)
    return pieces or _hard_split(text)


def _hard_split(text: str) -> list[str]:
    """Force-split text into MAX_PARAGRAPH_CHARS-sized pieces (last resort)."""
    return [text[i:i + MAX_PARAGRAPH_CHARS]
            for i in range(0, len(text), MAX_PARAGRAPH_CHARS)]


def _split_sentences(text: str) -> list[str]:
    """Split on 。！？.!? keeping the terminator. Filters empty fragments."""
    parts = re.split(r"(?<=[。！？.!?])", text)
    return [p for p in parts if p]


def _classify(text: str) -> Chunk:
    """Heuristically classify a chunk as paragraph / dialogue / description."""
    dialogue_marks = (
        text.count('"') + text.count('"') + text.count('"')
        + text.count('「') + text.count('」')
        + text.count('『') + text.count('』')
    )
    if dialogue_marks >= 3:
        ctype = "dialogue"
    elif sum(text.count(m) for m in _DESCRIPTION_MARKERS) >= 2:
        ctype = "description"
    else:
        ctype = "paragraph"
    return Chunk(text=text, chunk_type=ctype, char_count=len(text))
