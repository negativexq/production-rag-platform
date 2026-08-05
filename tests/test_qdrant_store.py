from qdrant_client import QdrantClient

from app.ingestion.models import Chunk
from app.ingestion.qdrant_store import EMBEDDING_DIM, VECTOR_NAME, QdrantStore

COLLECTION = "test_chunks"


def _store() -> QdrantStore:
    client = QdrantClient(":memory:")
    store = QdrantStore(client=client, collection_name=COLLECTION)
    store.ensure_collection()
    return store


def _chunk(doc_id="doc1", page=1, paragraph=0, char_range=(0, 10), text="hello world"):
    return Chunk(
        doc_id=doc_id,
        page_number=page,
        paragraph_index=paragraph,
        char_range=char_range,
        text=text,
    )


def _vector(seed: float = 0.1) -> list[float]:
    return [seed] * EMBEDDING_DIM


def test_ensure_collection_creates_dense_cosine_vector_of_correct_size():
    store = _store()

    info = store._client.get_collection(COLLECTION)
    vector_params = info.config.params.vectors[VECTOR_NAME]

    assert vector_params.size == EMBEDDING_DIM
    assert vector_params.distance.name == "COSINE"


def test_ensure_collection_is_idempotent():
    store = _store()

    store.ensure_collection()
    store.ensure_collection()

    assert store.count() == 0


def test_upsert_chunks_writes_one_point_per_chunk_with_correct_payload():
    store = _store()
    chunk = _chunk()

    store.upsert_chunks([chunk], [_vector()], source_filename="doc1.pdf")

    assert store.count() == 1
    point = store._client.retrieve(COLLECTION, ids=[QdrantStore.point_id_for(chunk)])[0]
    assert point.payload == {
        "doc_id": chunk.doc_id,
        "page_number": chunk.page_number,
        "paragraph_index": chunk.paragraph_index,
        "char_range": list(chunk.char_range),
        "text": chunk.text,
        "source_filename": "doc1.pdf",
    }


def test_upserting_the_same_chunk_twice_does_not_duplicate():
    store = _store()
    chunk = _chunk()

    store.upsert_chunks([chunk], [_vector()], source_filename="doc1.pdf")
    store.upsert_chunks([chunk], [_vector()], source_filename="doc1.pdf")

    assert store.count() == 1


def test_different_chunks_produce_different_point_ids():
    chunk_a = _chunk(char_range=(0, 10))
    chunk_b = _chunk(char_range=(10, 20))

    assert QdrantStore.point_id_for(chunk_a) != QdrantStore.point_id_for(chunk_b)


def test_point_id_is_deterministic_for_same_chunk_fields():
    chunk_a = _chunk()
    chunk_b = _chunk()

    assert QdrantStore.point_id_for(chunk_a) == QdrantStore.point_id_for(chunk_b)
