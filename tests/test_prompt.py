from app.llm.prompt import NOT_FOUND_PHRASE, build_context, build_messages
from app.retrieval.hybrid_search import SearchResult


def _result(page: int, paragraph: int, text: str) -> SearchResult:
    return SearchResult(
        score=0.9, payload={"page_number": page, "paragraph_index": paragraph, "text": text}
    )


def test_build_context_labels_each_chunk_with_page_and_paragraph():
    chunks = [
        _result(2, 0, "First chunk text."),
        _result(5, 1, "Second chunk text."),
    ]

    context = build_context(chunks)

    assert "Sayfa 2, Paragraf 0" in context
    assert "Sayfa 5, Paragraf 1" in context
    assert "First chunk text." in context
    assert "Second chunk text." in context


def test_build_context_empty_chunks_produces_empty_string():
    assert build_context([]) == ""


def test_build_messages_includes_system_and_user_roles():
    chunks = [_result(1, 0, "Some context.")]

    messages = build_messages("What is this about?", chunks)

    roles = [m["role"] for m in messages]
    assert roles == ["system", "user"]
    assert "What is this about?" in messages[1]["content"]
    assert "Some context." in messages[1]["content"]


def test_build_messages_system_prompt_mentions_citation_format_and_not_found_phrase():
    messages = build_messages("question", [_result(1, 0, "text")])

    system_content = messages[0]["content"]
    assert "[s." in system_content
    assert NOT_FOUND_PHRASE in system_content
