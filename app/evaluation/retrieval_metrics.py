from dataclasses import dataclass

from app.retrieval.hybrid_search import SearchResult

Location = tuple[int, int]


@dataclass(frozen=True)
class RetrievalMetrics:
    precision: float
    recall: float
    retrieved_locations: list[Location]
    expected_locations: list[Location]


def compute_retrieval_metrics(
    retrieved: list[SearchResult], expected_locations: list[Location]
) -> RetrievalMetrics:
    """Deterministic, non-LLM-judged context precision/recall: since the
    golden set specifies exact (page, paragraph) ground truth per question,
    classic set-overlap IR metrics apply directly — no judge model needed
    for retrieval quality.
    """
    retrieved_locations = [
        (r.payload["page_number"], r.payload["paragraph_index"]) for r in retrieved
    ]
    retrieved_set = set(retrieved_locations)
    expected_set = set(expected_locations)
    true_positives = len(retrieved_set & expected_set)

    precision = true_positives / len(retrieved_set) if retrieved_set else 0.0
    recall = true_positives / len(expected_set) if expected_set else 0.0

    return RetrievalMetrics(
        precision=precision,
        recall=recall,
        retrieved_locations=retrieved_locations,
        expected_locations=expected_locations,
    )
