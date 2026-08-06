import asyncio
import tempfile
from pathlib import Path

from app.ingestion.cli import run_ingestion
from app.ingestion.ingest import IngestStats


def ingest_uploaded_file(filename: str, content: bytes) -> IngestStats:
    """Thin sync wrapper around the real ingestion pipeline
    (app.ingestion.cli.run_ingestion) for Streamlit, which has no async
    event loop of its own. Writes the upload to a temp dir (ingest_path
    scans a folder for *.pdf) and reuses the exact same code path as
    `make ingest`.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / filename
        pdf_path.write_bytes(content)
        return asyncio.run(run_ingestion(tmp_dir))
