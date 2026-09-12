# 台灣華語老師 — dev/ops targets.
#
# Two ways to run the app:
#   Docker (recommended)  make up        — app + nightly backup cron, data on a named volume
#   Native Python         make setup run — venv + Vite build, data in ./data
#
# Backup/restore targets work with either; see README "Backups & restore".

SHELL := /bin/bash
PY := python3
VENV := backend/.venv
PYBIN := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# Load PORT from .env if present, else default to 3002.
PORT ?= $(shell [ -f .env ] && grep -E '^PORT=' .env | cut -d= -f2 || echo 3002)

# Backup/restore run inside the app container when it's up, else in the venv.
DOCKER_RUNNING := $(shell docker compose ps --status running --quiet app 2>/dev/null)
ifeq ($(DOCKER_RUNNING),)
  RUN_BACKEND := cd backend && ../$(VENV)/bin/python
else
  RUN_BACKEND := docker compose exec -T app python
endif

.PHONY: help
help:
	@echo "Run it (Docker — recommended):"
	@echo "  make up              Build + start app and backup cron (data on a named volume)"
	@echo "  make down            Stop containers — YOUR DATA IS KEPT"
	@echo "  make logs            Follow container logs"
	@echo "  make rebuild         Rebuild the image and restart (progress survives)"
	@echo ""
	@echo "Run it (native Python):"
	@echo "  make setup           Full first-run setup (venv, deps, frontend build)"
	@echo "  make run             Run FastAPI (serves API + built frontend) on \$$PORT ($(PORT))"
	@echo "  make dev-frontend    Run Vite dev server (proxies /api to backend)"
	@echo ""
	@echo "Backups & restore (spec §7):"
	@echo "  make backup          Take a snapshot + JSON export now"
	@echo "  make backup-status   When did a backup last run? How many are kept?"
	@echo "  make backups-list    List the backups on the data volume"
	@echo "  make export FILE=x   Export all progress to a JSON file on the host"
	@echo "  make import FILE=x   Merge a JSON export back in"
	@echo "  make restore FILE=x  Replace all progress from a JSON export"
	@echo ""
	@echo "Content pipeline (spec §5):"
	@echo "  make coverage        Per-unit completeness — what's taught, what's staged"
	@echo "  make load-content    Validate + load content/units/ into content.db"
	@echo "  make build-skeleton  Rebuild HSK 1-4 draft units from the word lists"
	@echo "  make generate-content  Fill in drafts via Claude (needs ANTHROPIC_API_KEY)"
	@echo "  make warm-audio      Pre-generate zh-TW audio for the live units"
	@echo ""
	@echo "Phone access:"
	@echo "  make tailscale-up    Serve the app over HTTPS on your tailnet"
	@echo "  make tailscale-down  Stop serving"
	@echo ""
	@echo "  make test            Run the backend test suite"
	@echo "  make clean           Remove venv, node_modules, and build output (NOT your data)"

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
.env:
	@cp .env.example .env
	@echo "Created .env from .env.example — edit it to add your Anthropic key."

.PHONY: up
up: .env
	docker compose up -d --build
	@echo ""
	@echo "✅ Running at http://localhost:$(PORT)"
	@echo "   Backups: nightly, kept 30 days, on the mandarin-data volume."
	@echo "   Phone access: make tailscale-up"

.PHONY: down
down:
	docker compose down
	@echo "Stopped. The mandarin-data volume (all your progress) is untouched."

.PHONY: logs
logs:
	docker compose logs -f

.PHONY: rebuild
rebuild:
	docker compose build --no-cache
	docker compose up -d
	@echo "Rebuilt from scratch. Progress data survived (it lives on the named volume)."

.PHONY: ps
ps:
	docker compose ps

# ---------------------------------------------------------------------------
# Native Python
# ---------------------------------------------------------------------------
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

.PHONY: test
test: $(VENV)
	cd backend && ../$(VENV)/bin/python -m pytest -q

# ---------------------------------------------------------------------------
# Backups & restore (spec §7)
#
# These auto-detect: if the app container is running they execute inside it
# (against the named volume), otherwise they use the local venv and ./data.
# ---------------------------------------------------------------------------
FILE ?= progress-export.json
# Resolved against the directory make was invoked from: the backup targets cd
# into backend/ (or exec into the container), so a relative path would otherwise
# resolve somewhere the user didn't mean.
FILE_ABS := $(abspath $(FILE))

.PHONY: backup
backup:
	$(RUN_BACKEND) -m scripts.backup

.PHONY: backup-status
backup-status:
	@$(RUN_BACKEND) -c "import json; from app import backup; print(json.dumps(backup.last_backup_info(), indent=2))"

.PHONY: backups-list
backups-list:
	@$(RUN_BACKEND) -c "from pathlib import Path; from app.config import get_settings; \
	    d = get_settings().backup_dir; \
	    print(f'{d}:'); \
	    [print(f'  {p.stat().st_size:>10,d}  {p.name}') for p in sorted(d.iterdir())] or print('  (empty)')"

.PHONY: export
export:
	@$(RUN_BACKEND) -m scripts.export_progress > "$(FILE_ABS)"
	@echo "Exported progress to $(FILE_ABS) ($$(wc -c < "$(FILE_ABS)") bytes)"
	@echo "Keep this file somewhere other than this machine."

.PHONY: import
import:
	@test -f "$(FILE_ABS)" || { echo "No such file: $(FILE_ABS)  (use: make import FILE=your-export.json)"; exit 1; }
	@echo "Merging $(FILE_ABS) into the current progress data…"
	@$(RUN_BACKEND) -m scripts.import_progress /dev/stdin < "$(FILE_ABS)"

.PHONY: restore
restore:
	@test -f "$(FILE_ABS)" || { echo "No such file: $(FILE_ABS)  (use: make restore FILE=your-export.json)"; exit 1; }
	@echo "This REPLACES all current progress with the contents of $(FILE_ABS)."
	@echo "A safety snapshot is taken first. Press Ctrl-C within 5s to abort."
	@sleep 5
	@$(RUN_BACKEND) -m scripts.import_progress /dev/stdin --replace < "$(FILE_ABS)"

# ---------------------------------------------------------------------------
# Content pipeline (spec §5)
#
# The app ships with its curriculum committed and loaded, so none of these are
# needed to run it. They are authoring tools.
# ---------------------------------------------------------------------------
.PHONY: coverage
coverage:
	@$(RUN_BACKEND) -m scripts.coverage $(ARGS)

.PHONY: load-content
load-content:
	$(RUN_BACKEND) -m scripts.load_content $(ARGS)

.PHONY: check-content
check-content:
	$(RUN_BACKEND) -m scripts.load_content --check

.PHONY: build-skeleton
build-skeleton:
	$(RUN_BACKEND) -m scripts.build_skeleton --theme offline $(ARGS)
	@echo ""
	@echo "Drafts are staged, not taught. Next: make generate-content"

.PHONY: generate-content
generate-content:
	$(RUN_BACKEND) -m scripts.generate_content $(ARGS)

.PHONY: warm-audio
warm-audio:
	$(RUN_BACKEND) -m scripts.warm_audio $(ARGS)

# ---------------------------------------------------------------------------
# Phone access
# ---------------------------------------------------------------------------
.PHONY: tailscale-up serve-tailscale
tailscale-up serve-tailscale:
	@./scripts/tailscale-serve.sh $(PORT)

.PHONY: tailscale-down
tailscale-down:
	@./scripts/tailscale-serve.sh --off

.PHONY: tailscale-status
tailscale-status:
	@./scripts/tailscale-serve.sh --status

# ---------------------------------------------------------------------------
.PHONY: clean
clean:
	rm -rf $(VENV) frontend/node_modules frontend/dist frontend/dev-dist
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "Cleaned build artefacts. ./data and the mandarin-data volume were NOT touched."
