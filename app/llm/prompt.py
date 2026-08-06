import re
from pathlib import Path

from app.retrieval.hybrid_search import SearchResult

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
NOT_FOUND_PHRASE = "I could not find this in the document."


def load_system_prompt(version: str) -> str:
    path = PROMPTS_DIR / f"answer_{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"No prompt template for version {version!r}: {path}")
    return path.read_text().format(not_found_phrase=NOT_FOUND_PHRASE)


def doc_label(source_filename: str) -> str:
    """Short, citation-tag-safe identifier for a source document, derived
    from its filename (extension stripped, non-word characters collapsed).
    Shared by build_context (what the LLM sees) and grounding.py (what a
    citation is validated against) so a citation can be checked against the
    SAME document it claims — two documents in one collection can otherwise
    share (page, paragraph) coordinates. See docs/PLANNING.md Sprint 11
    post-release bug fix note.
    """
    stem = source_filename.rsplit(".", 1)[0] if "." in source_filename else source_filename
    return re.sub(r"[^\w\-]", "_", stem) or "doc"


def build_context(chunks: list[SearchResult]) -> str:
    parts = []
    for chunk in chunks:
        payload = chunk.payload
        doc = doc_label(payload.get("source_filename", "doc"))
        label = (
            f"[Kaynak: {doc}, Sayfa {payload['page_number']}, "
            f"Paragraf {payload['paragraph_index']}]"
        )
        parts.append(f"{label}\n{payload['text']}")
    return "\n\n".join(parts)


def build_messages(question: str, chunks: list[SearchResult], version: str) -> list[dict]:
    system_prompt = load_system_prompt(version)
    context = build_context(chunks)
    user_content = f"Context:\n{context}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
