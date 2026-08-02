# BookBuddy backend startup

BookBuddy has two supported ASGI launch forms:

```powershell
.\venv\Scripts\python.exe backend\main.py
.\venv\Scripts\python.exe -m uvicorn --app-dir backend app:app
```

`backend/main.py` is the canonical process launcher. `app:create_app` is available for
tests and embedding. Frontends only need to manage the backend process and do
not need to know which AI provider is configured.

Runtime settings are loaded from `.env` and then overridden by process
environment variables. Important settings are `BOOKBUDDY_HOST` (default
`127.0.0.1`), `BOOKBUDDY_PORT` (default `8000`),
`BOOKBUDDY_LIBRARY_DIR`, `BOOKBUDDY_CACHE_DIR`, `BOOKBUDDY_LOG_DIR`, and
`BOOKBUDDY_SHUTDOWN_TIMEOUT_SECONDS` (default `30`). Relative paths are
resolved from the repository root.

The core backend can start without an AI provider. Gemini support is optional:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements\requirements-ai-gemini.txt
```

Existing `GEMINI_API_KEY*` credentials configure text generation and
`GEMINI_VISION_API_KEY*` credentials configure the isolated, opt-in vision
pool. Missing provider dependencies or credentials leave non-AI routes,
cached data, replay, and local dictionary/image behavior available.

`backend/gemini_test.py` is a developer-only connectivity diagnostic. It never starts
the application or parses a book and sends a probe only after confirmation.
