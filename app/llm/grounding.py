import re
from dataclasses import dataclass

from app.retrieval.hybrid_search import SearchResult

_CITATION_RE = re.compile(r"\[s\.(\d+)/(\d+)\]")


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    citations_found: list[tuple[int, int]]
    ungrounded_citations: list[tuple[int, int]]


def check_grounding(answer: str, chunks: list[SearchResult]) -> GroundingResult:
    """Post-hoc check: does every [s.<page>/<paragraph>] citation in the
    answer correspond to a chunk that was actually in the context? Runs
    after generation completes — see docs/PLANNING.md Sprint 6 closing note
    for why a failure here warns rather than blocks the (already streamed)
    answer.
    """
    valid_locations = {(c.payload["page_number"], c.payload["paragraph_index"]) for c in chunks}

    citations_found = [
        (int(page), int(paragraph)) for page, paragraph in _CITATION_RE.findall(answer)
    ]
    ungrounded_citations = [c for c in citations_found if c not in valid_locations]

    return GroundingResult(
        grounded=len(ungrounded_citations) == 0,
        citations_found=citations_found,
        ungrounded_citations=ungrounded_citations,
    )
