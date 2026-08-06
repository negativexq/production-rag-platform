import re
from dataclasses import dataclass

from app.llm.prompt import doc_label
from app.retrieval.hybrid_search import SearchResult

_CITATION_RE = re.compile(r"\[s\.([\w\-]+):(\d+)/(\d+)\]")


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    citations_found: list[tuple[str, int, int]]
    ungrounded_citations: list[tuple[str, int, int]]


def check_grounding(answer: str, chunks: list[SearchResult]) -> GroundingResult:
    """Post-hoc check: does every [s.<doc>:<page>/<paragraph>] citation in
    the answer correspond to a chunk that was actually in the context, from
    the SAME document? Runs after generation completes — see
    docs/PLANNING.md Sprint 6 closing note for why a failure here warns
    rather than blocks the (already streamed) answer.

    The doc component is required (not just page/paragraph) because two
    different documents in the same collection can share the same
    (page, paragraph) coordinates — see the Sprint 11 post-release bug fix
    note in docs/PLANNING.md.
    """
    valid_locations = {
        (
            doc_label(c.payload.get("source_filename", "doc")),
            c.payload["page_number"],
            c.payload["paragraph_index"],
        )
        for c in chunks
    }

    citations_found = [
        (doc, int(page), int(paragraph)) for doc, page, paragraph in _CITATION_RE.findall(answer)
    ]
    ungrounded_citations = [c for c in citations_found if c not in valid_locations]

    return GroundingResult(
        grounded=len(ungrounded_citations) == 0,
        citations_found=citations_found,
        ungrounded_citations=ungrounded_citations,
    )
