.PHONY: dev test lint up down ingest ui

VENV := .venv/bin
VENV_UI := .venv-ui/bin

dev:
	$(VENV)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	$(VENV)/pytest -q

lint:
	$(VENV)/ruff check app tests

up:
	docker compose up -d

down:
	docker compose down

ingest:
	$(VENV)/python -m app.ingestion.cli --path $(PATH_ARG)

ui:
	PYTHONPATH=. $(VENV_UI)/streamlit run app/ui/streamlit_app.py
