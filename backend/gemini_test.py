"""Developer-only diagnostic for the configured Gemini provider.

Importing this module performs no dependency check, client construction,
filesystem mutation, or network request.
"""

from __future__ import annotations

import time


def main() -> int:
    from ai import GenerationRequest
    from ai import create_ai_manager
    from config import load_config

    config = load_config()
    manager = create_ai_manager(config)
    try:
        print("BookBuddy AI provider diagnostic")
        print(f"Configured provider: {config.ai.provider}")
        if not manager.is_available("text"):
            print("Text generation is unavailable. Check the optional provider dependency and credentials.")
            return 2
        answer = input("Send one small connectivity probe? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("No request sent.")
            return 0
        started = time.monotonic()
        result = manager.generate(GenerationRequest(
            role="dictionary",
            prompt="Reply with exactly: BookBuddy provider ready",
            temperature=0.0,
        ))
        elapsed = time.monotonic() - started
        print(f"Provider: {result.provider}")
        print(f"Model: {result.model}")
        print(f"Latency: {elapsed:.2f}s")
        print(f"Attempts: {result.attempts}")
        print(f"Response: {result.text[:200]}")
        if result.usage:
            print(f"Usage fields: {', '.join(sorted(result.usage))}")
        return 0
    except Exception as exc:
        print(f"Diagnostic failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
