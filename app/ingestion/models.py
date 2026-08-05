from dataclasses import dataclass


@dataclass(frozen=True)
class Paragraph:
    page_number: int
    paragraph_index: int
    text: str


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    page_number: int
    paragraph_index: int
    char_range: tuple[int, int]
    text: str
