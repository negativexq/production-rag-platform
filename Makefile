.PHONY: dev test lint up down

VENV := .venv/bin

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
