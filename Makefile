# 台灣華語老師 — dev/ops targets.
# Phase 0: scaffold, install, build, run. Later phases extend `setup`
# (CC-CEDICT + Whisper download, content generation).

SHELL := /bin/bash
PY := python3
VENV := backend/.venv
PYBIN := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# Load PORT from .env if present, else default to 3002.
PORT ?= $(shell [ -f .env ] && grep -E '^PORT=' .env | cut -d= -f2 || echo 3002)

.PHONY: help
help:
	@echo "Targets:"
	@echo "  make setup           Full first-run setup (venv, deps, frontend build)"
	@echo "  make backend-deps    Create venv and install backend requirements"
	@echo "  make frontend-deps   npm install in frontend/"
	@echo "  make build-frontend  Build the Vite frontend into frontend/dist"
	@echo "  make dev-backend     Run FastAPI (serves API + built frontend) on \$$PORT ($(PORT))"
	@echo "  make dev-frontend    Run Vite dev server (proxies /api to backend)"
	@echo "  make run             Alias for dev-backend (production-style single process)"
	@echo "  make serve-tailscale Print the Tailscale Serve command for phone access"
	@echo "  make clean           Remove venv, node_modules, and build output"

.PHONY: setup
setup: backend-deps frontend-deps build-frontend
	@echo ""
	@echo "✅ Setup complete. Start the app with:  make run"
	@echo "   Then open http://localhost:$(PORT)"

$(VENV):
	$(PY) -m venv $(VENV)

.PHONY: backend-deps
backend-deps: $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt

.PHONY: frontend-deps
frontend-deps:
	cd frontend && npm install

.PHONY: build-frontend
build-frontend:
	cd frontend && npm run build

.PHONY: dev-backend run
dev-backend run: $(VENV)
	cd backend && PORT=$(PORT) ../$(VENV)/bin/python -m app

.PHONY: dev-frontend
dev-frontend:
	cd frontend && PORT=$(PORT) npm run dev

.PHONY: serve-tailscale
serve-tailscale:
	@echo "Run this to expose the app over HTTPS to your phone:"
	@echo "  tailscale serve $(PORT)"

.PHONY: clean
clean:
	rm -rf $(VENV) frontend/node_modules frontend/dist frontend/dev-dist
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +
