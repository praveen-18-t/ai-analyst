.PHONY: up down test backend-dev frontend-dev sample
up:            ## run everything in Docker
	docker compose up --build
down:
	docker compose down
test:
	cd backend && pip install -q -r requirements-dev.txt && pytest -q
backend-dev:   ## API on :8000 with SQLite + local files (no Docker)
	cd backend && pip install -q -r requirements.txt && DATABASE_URL=sqlite:///./data/app.db uvicorn app.main:app --reload --port 8000
frontend-dev:  ## UI on :3000, proxied to the API
	cd frontend && npm install && API_PROXY_TARGET=http://localhost:8000 npm run dev
sample:
	python3 scripts/make_sample_data.py
