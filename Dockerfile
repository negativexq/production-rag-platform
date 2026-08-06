FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# sentence-transformers pulls torch as a transitive dependency; on
# manylinux aarch64 pip defaults to the CUDA-enabled build (~2GB of
# nvidia_* wheels) even though this container has no GPU (Ollama runs
# native on the host, see docs/PLANNING.md Sprint 10). Installing the
# CPU-only wheel first makes the requirements.txt install below see torch
# already satisfied and skip the CUDA variant entirely.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY prompts/ ./prompts/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
