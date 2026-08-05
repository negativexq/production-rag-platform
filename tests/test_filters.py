from qdrant_client.http import models as qmodels

from app.retrieval.filters import build_filter


def test_build_filter_returns_none_when_nothing_given():
    assert build_filter() is None
    assert build_filter(doc_ids=None, source_filenames=None, page_numbers=None) is None
    assert build_filter(doc_ids=[], source_filenames=[], page_numbers=[]) is None


def test_build_filter_single_field():
    result = build_filter(doc_ids=["doc1", "doc2"])

    assert isinstance(result, qmodels.Filter)
    assert len(result.must) == 1
    condition = result.must[0]
    assert condition.key == "doc_id"
    assert condition.match == qmodels.MatchAny(any=["doc1", "doc2"])


def test_build_filter_combines_fields_with_and():
    result = build_filter(doc_ids=["doc1"], source_filenames=["a.pdf", "b.pdf"])

    assert len(result.must) == 2
    keys = {c.key for c in result.must}
    assert keys == {"doc_id", "source_filename"}


def test_build_filter_page_numbers():
    result = build_filter(page_numbers=[1, 2])

    condition = result.must[0]
    assert condition.key == "page_number"
    assert condition.match == qmodels.MatchAny(any=[1, 2])
