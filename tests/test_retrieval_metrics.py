from app.evaluation.retrieval_metrics import compute_retrieval_metrics
from app.retrieval.hybrid_search import SearchResult


def _result(page: int, paragraph: int) -> SearchResult:
    return SearchResult(score=0.9, payload={"page_number": page, "paragraph_index": paragraph})


def test_perfect_retrieval_gives_precision_and_recall_of_one():
    retrieved = [_result(1, 0), _result(2, 1)]
    metrics = compute_retrieval_metrics(retrieved, expected_locations=[(1, 0), (2, 1)])

    assert metrics.precision == 1.0
    assert metrics.recall == 1.0


def test_extra_irrelevant_chunk_lowers_precision_but_not_recall():
    retrieved = [_result(1, 0), _result(9, 9)]  # (9,9) is irrelevant noise
    metrics = compute_retrieval_metrics(retrieved, expected_locations=[(1, 0)])

    assert metrics.precision == 0.5
    assert metrics.recall == 1.0


def test_missing_expected_chunk_lowers_recall_but_not_precision():
    retrieved = [_result(1, 0)]
    metrics = compute_retrieval_metrics(retrieved, expected_locations=[(1, 0), (2, 1)])

    assert metrics.precision == 1.0
    assert metrics.recall == 0.5


def test_multi_chunk_expected_locations_all_found():
    retrieved = [_result(2, 1), _result(5, 1), _result(3, 0)]
    metrics = compute_retrieval_metrics(retrieved, expected_locations=[(2, 1), (5, 1)])

    assert metrics.recall == 1.0
    assert metrics.precision == 2 / 3


def test_no_retrieved_results_gives_zero_precision():
    metrics = compute_retrieval_metrics([], expected_locations=[(1, 0)])

    assert metrics.precision == 0.0
    assert metrics.recall == 0.0


def test_records_retrieved_and_expected_locations():
    retrieved = [_result(1, 0)]
    metrics = compute_retrieval_metrics(retrieved, expected_locations=[(1, 0)])

    assert metrics.retrieved_locations == [(1, 0)]
    assert metrics.expected_locations == [(1, 0)]
