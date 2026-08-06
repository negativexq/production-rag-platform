from app.llm.grounding import check_grounding
from app.retrieval.hybrid_search import SearchResult


def _result(page: int, paragraph: int, text: str, source_filename: str = "doc.pdf") -> SearchResult:
    return SearchResult(
        score=0.9,
        payload={
            "page_number": page,
            "paragraph_index": paragraph,
            "text": text,
            "source_filename": source_filename,
        },
    )


def test_grounding_passes_when_all_citations_match_context():
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]
    answer = "Refunds take 30 days [s.doc:2/0]."

    result = check_grounding(answer, chunks)

    assert result.grounded is True
    assert result.citations_found == [("doc", 2, 0)]
    assert result.ungrounded_citations == []


def test_grounding_fails_on_a_deliberately_fabricated_citation():
    """Concrete proof the check actually catches hallucination: context only
    has (page=2, paragraph=0), but the answer cites a page/paragraph
    (99, 0) that was never in the context — a fabricated reference.
    """
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]
    fabricated_answer = "Refunds take 30 days [s.doc:99/0]."

    result = check_grounding(fabricated_answer, chunks)

    assert result.grounded is False
    assert result.ungrounded_citations == [("doc", 99, 0)]


def test_grounding_reports_only_the_fabricated_citation_when_mixed():
    chunks = [_result(2, 0, "Refunds are processed within 30 days."), _result(5, 1, "Other text.")]
    answer = "Refunds take 30 days [s.doc:2/0], and something else [s.doc:5/1], plus [s.doc:7/3]."

    result = check_grounding(answer, chunks)

    assert result.grounded is False
    assert result.citations_found == [("doc", 2, 0), ("doc", 5, 1), ("doc", 7, 3)]
    assert result.ungrounded_citations == [("doc", 7, 3)]


def test_grounding_with_no_citations_at_all_is_considered_grounded():
    # e.g. the "not found in document" reply has no citations to check
    chunks = [_result(2, 0, "Refunds are processed within 30 days.")]

    result = check_grounding("I could not find this in the document.", chunks)

    assert result.grounded is True
    assert result.citations_found == []


def test_grounding_rejects_citation_whose_page_paragraph_matches_a_different_document():
    """Regression test for a real bug: a two-document collection (a CV and
    an unrelated handbook) can share the same (page, paragraph) coordinates.
    A citation must be validated against the SAME document it claims, not
    just against any chunk with matching page/paragraph anywhere in context.
    """
    chunks = [
        _result(1, 0, "CV text about Python and SQL.", source_filename="cv.pdf"),
        _result(2, 0, "Unrelated handbook text.", source_filename="handbook.pdf"),
    ]
    # cites handbook's coordinates (2, 0) but tags it as coming from the cv
    answer = "Knows Python and SQL [s.cv:2/0]."

    result = check_grounding(answer, chunks)

    assert result.grounded is False
    assert result.ungrounded_citations == [("cv", 2, 0)]
