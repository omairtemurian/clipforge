# ffmpeg-full (keg-only, with libass/freetype) must win over plain Homebrew ffmpeg.
export PATH := /opt/homebrew/opt/ffmpeg-full/bin:$(PATH)

.PHONY: setup dev test lint check check-engines e2e

setup:
	uv sync
	uv run python scripts/download_models.py
	npm --prefix frontend ci
	npm ci
	npx playwright install chromium

dev:
	@set -e; \
	uv run uvicorn clipforge.api.app:app --host 127.0.0.1 --port 8000 & backend_pid=$$!; \
	npm --prefix frontend run dev -- --host 127.0.0.1 & frontend_pid=$$!; \
	trap 'kill $$backend_pid $$frontend_pid 2>/dev/null || true' EXIT INT TERM; \
	wait

test:
	uv run pytest backend/tests
	npm --prefix frontend run test -- --run

lint:
	uv run ruff check backend scripts
	uv run ruff format --check backend scripts
	uv run mypy --strict backend/clipforge scripts/download_models.py scripts/gen_types.py scripts/check_parity.py scripts/fetch_starter_sfx.py
	uv run python scripts/gen_types.py --check
	uv run python scripts/check_parity.py scripts/fetch_starter_sfx.py
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck
	npm --prefix frontend exec -- prettier --check frontend

check: lint test
	npm --prefix frontend run build

# Playwright end to end tests: the backend runs in test mode (see
# clipforge.api.testapp) next to vite; stop `make dev` first (ports 8000, 5173).
e2e:
	npx playwright test -c e2e

# Optional engines (SPEC-v2 2.3): runs the engine_* tests; an engine that is
# not installed skips its test with the reason.
ENGINE_MARKERS = engine_ollama_vlm or engine_deepfilternet or engine_kokoro or engine_piper or engine_demucs or engine_image_gen or engine_realesrgan or engine_voice_clone or engine_yamnet or engine_segment or engine_embeddings or engine_claude_code
check-engines:
	uv run pytest backend/tests -m "$(ENGINE_MARKERS)" -rs
