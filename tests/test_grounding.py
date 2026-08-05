from app.llm.grounding import check_grounding
from app.retrieval.hybrid_search import SearchResult


def _result(page: int, paragraph: int, text: str) -> SearchResult:
    return SearchResult(
        score=0.9, payload={"page_number": page, "paragraph_index": paragraph, "text": text}
    )


def test_grounding_passes_when_all_citations_match_context():
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]
    answer = "Refunds take 30 days [s.2/0]."

    result = check_grounding(answer, chunks)

    assert result.grounded is True
    assert result.citations_found == [(2, 0)]
    assert result.ungrounded_citations == []


def test_grounding_fails_on_a_deliberately_fabricated_citation():
    """Concrete proof the check actually catches hallucination: context only
    has (page=2, paragraph=0), but the answer cites a page/paragraph
    (99, 0) that was never in the context — a fabricated reference.
    """
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]
    fabricated_answer = "Refunds take 30 days [s.99/0]."

    result = check_grounding(fabricated_answer, chunks)

    assert result.grounded is False
    assert result.ungrounded_citations == [(99, 0)]


def test_grounding_reports_only_the_fabricated_citation_when_mixed():
    chunks = [_result(2, 0, "Refunds are processed within 30 days."), _result(5, 1, "Other text.")]
    answer = "Refunds take 30 days [s.2/0], and something else [s.5/1], plus [s.7/3]."

    result = check_grounding(answer, chunks)

    assert result.grounded is False
    assert result.citations_found == [(2, 0), (5, 1), (7, 3)]
    assert result.ungrounded_citations == [(7, 3)]


def test_grounding_with_no_citations_at_all_is_considered_grounded():
    # e.g. the "not found in document" reply has no citations to check
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]

    result = check_grounding("I could not find this in the document.", chunks)

    assert result.grounded is True
    assert result.citations_found == []
