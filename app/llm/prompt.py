from app.retrieval.hybrid_search import SearchResult

# v1 — a single hardcoded version for this sprint. Sprint 7 moves this to a
# versioned file under prompts/ (answer_v1.txt, answer_v2.txt, ...).
NOT_FOUND_PHRASE = "I could not find this in the document."

SYSTEM_PROMPT_V1 = f"""You are a helpful assistant that answers questions using ONLY the \
provided context below. Do not use any outside knowledge.

CITATION RULE: after every sentence that uses information from the context, you MUST \
insert a citation tag in this EXACT literal format: [s.PAGE/PARAGRAPH]
For example, if you use information labeled "[Kaynak: Sayfa 3, Paragraf 0]", you write \
[s.3/0] right after the sentence. Copy the numbers exactly. Do not write "Kaynak", \
"Sayfa", or "Paragraf" in your answer — only use the short [s.PAGE/PARAGRAPH] tag.

If the context does not contain the answer to the question, reply with exactly this \
sentence and nothing else: "{NOT_FOUND_PHRASE}\""""


def build_context(chunks: list[SearchResult]) -> str:
    parts = []
    for chunk in chunks:
        payload = chunk.payload
        label = f"[Kaynak: Sayfa {payload['page_number']}, Paragraf {payload['paragraph_index']}]"
        parts.append(f"{label}\n{payload['text']}")
    return "\n\n".join(parts)


def build_messages(question: str, chunks: list[SearchResult]) -> list[dict]:
    context = build_context(chunks)
    user_content = f"Context:\n{context}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT_V1},
        {"role": "user", "content": user_content},
    ]
