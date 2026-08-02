import asyncio
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import json
from unittest import mock

from fastapi.testclient import TestClient

from ai import AIManager, GenerationRequest, PermanentAIError, QuotaExhaustedError
from ai.models import ProviderResponse
from app import create_app
from bootstrap import TaskSupervisor
from config import AIConfig, ContractConfig, load_config
from session_manager import SessionManager


class FakeProvider:
    name = "fake"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.closed = 0

    def is_available(self, capability):
        return True

    def generate(self, request, *, model):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self):
        self.closed += 1


class StartupArchitectureTests(unittest.TestCase):
    def test_release_versions_are_aligned(self):
        root = Path(__file__).resolve().parents[1]
        canonical = json.loads((root / "config" / "version.json").read_text(encoding="utf-8"))
        package = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
        tauri = json.loads((root / "frontend" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        cargo = (root / "frontend" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
        self.assertEqual("bookbuddy_version_v1", canonical["schema_version"])
        self.assertIn(f'version = "{canonical["version"]}"', cargo)
        self.assertEqual(canonical["version"], package["version"])
        self.assertEqual(package["version"], tauri["version"])
        self.assertEqual(package["version"], ContractConfig().bookbuddy_version)

    def test_backend_bundle_includes_canonical_version_metadata(self):
        root = Path(__file__).resolve().parents[1]
        spec = (root / "packaging" / "bookbuddy-backend.spec").read_text(encoding="utf-8")
        self.assertIn(
            '(str(root / "config" / "version.json"), "config")',
            spec,
        )

    def test_nsis_installs_beside_the_installer(self):
        root = Path(__file__).resolve().parents[1]
        tauri = json.loads((root / "frontend" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        nsis = tauri["bundle"]["windows"]["nsis"]
        self.assertEqual("./installer-hooks.nsh", nsis["installerHooks"])
        self.assertNotIn("externalBin", tauri["bundle"])
        hooks = (root / "frontend" / "src-tauri" / "installer-hooks.nsh").read_text(encoding="utf-8")
        self.assertIn('StrCpy $INSTDIR "$EXEDIR\\BookBuddy"', hooks)
        self.assertIn('CopyFiles /SILENT "$EXEPATH" "$INSTDIR\\$EXEFILE"', hooks)

    def test_desktop_executable_embeds_the_backend(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        self.assertIn("const EMBEDDED_BACKEND", source)
        self.assertIn("relocate_portable_executable", source)
        self.assertIn('root.join("runtime")', source)

    def config(self, root, extra=None):
        values = {
            "BOOKBUDDY_LIBRARY_DIR": "runtime/library",
            "BOOKBUDDY_CACHE_DIR": "runtime/cache",
            "BOOKBUDDY_LOG_DIR": "runtime/logs",
        }
        values.update(extra or {})
        return load_config(root, values)

    def test_configuration_is_frozen_anchored_redacted_and_environment_wins(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, ".env").write_text("BOOKBUDDY_PORT=7000\nGEMINI_API_KEY_1=dotenv-secret\n", encoding="utf-8")
            config = self.config(root, {"BOOKBUDDY_PORT": "8123", "GEMINI_API_KEY_1": "process-secret"})
            self.assertEqual(8123, config.server.port)
            self.assertEqual(Path(root, "runtime/library").resolve(), config.paths.library_dir)
            self.assertNotIn("process-secret", repr(config))
            with self.assertRaises(FrozenInstanceError):
                config.server.port = 9000

    def test_app_preserves_route_inventory_and_starts_without_ai(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.config(root)
            api = create_app(config)
            application_routes = [
                route for route in api.routes
                if getattr(route, "name", "") not in {"openapi", "swagger_ui_html", "swagger_ui_redirect", "redoc_html"}
            ]
            self.assertGreaterEqual(len(application_routes), 49)
            paths = {route.path for route in application_routes}
            self.assertIn("/reader/{user_id}/library-state", paths)
            self.assertIn("/reader/{book_name}/{session_name}/cover", paths)
            self.assertIn("/reader/{book_name}/{session_name}/explain-selection", paths)
            self.assertIn("/tasks", paths)
            self.assertIn("/reader/{user_id}/books/{book_name}/{session_name}/annotations", paths)
            with TestClient(api) as client:
                self.assertEqual({"status": "online"}, client.get("/").json())
                self.assertFalse(client.app.state.services.ai_manager.is_available("text"))

    def test_new_analysis_returns_structured_503_when_ai_is_unavailable(self):
        with tempfile.TemporaryDirectory() as root:
            api = create_app(self.config(root))
            with TestClient(api) as client:
                services = client.app.state.services
                services.session_manager.sessions["Book::reading"] = SimpleNamespace(total_chapters=1)
                response = client.post("/analyze/Book/reading/0")
                self.assertEqual(503, response.status_code)
                self.assertEqual(
                    {"code": "ai_service_unavailable", "capability": "chapter_analysis"},
                    response.json()["detail"],
                )

    def test_translation_is_explicit_and_degrades_without_ai(self):
        with tempfile.TemporaryDirectory() as root:
            api = create_app(self.config(root))
            with TestClient(api) as client:
                with mock.patch("app._require_reader_session", return_value="Book::reading"):
                    response = client.post("/reader/Book/reading/translate-selection", json={"selected_text": "Hello", "target_language": "Spanish"})
                self.assertEqual(503, response.status_code)
                self.assertEqual(
                    {"code": "ai_service_unavailable", "capability": "translation"},
                    response.json()["detail"],
                )

    def test_ai_manager_retries_quota_and_returns_neutral_metadata(self):
        provider = FakeProvider([
            QuotaExhaustedError("quota"),
            ProviderResponse(parsed={"ok": True}, provider="fake", model="model", credential_id="key-2"),
        ])
        manager = AIManager(AIConfig(max_retries=2, pacing_seconds=0, key_cooldown_seconds=0), provider)
        with mock.patch.object(manager._closing, "wait", return_value=False):
            result = manager.generate(GenerationRequest(role="chapter_analysis", prompt="x"))
        self.assertEqual({"ok": True}, result.parsed)
        self.assertEqual(2, result.attempts)
        self.assertEqual("key-2", result.credential_id)
        manager.close()
        manager.close()
        self.assertEqual(1, provider.closed)

    def test_ai_manager_does_not_retry_permanent_failure(self):
        provider = FakeProvider([PermanentAIError("invalid")])
        manager = AIManager(AIConfig(max_retries=5, pacing_seconds=0), provider)
        with self.assertRaises(PermanentAIError):
            manager.generate(GenerationRequest(role="chapter_analysis", prompt="x"))
        self.assertEqual(1, provider.calls)

    def test_main_import_has_no_launcher_side_effect(self):
        import main
        with mock.patch("dependency_manager.ensure_dependencies") as ensure:
            self.assertTrue(callable(main.main))
            ensure.assert_not_called()

    def test_python_launcher_passes_configuration_to_uvicorn(self):
        import main
        configured = SimpleNamespace(server=SimpleNamespace(
            host="127.0.0.9", port=9123, log_level="WARNING", shutdown_timeout_seconds=17,
        ))
        with mock.patch("dependency_manager.ensure_dependencies") as ensure, mock.patch(
            "config.load_config", return_value=configured
        ), mock.patch("uvicorn.run") as run:
            self.assertEqual(0, main.main())
        from app import app as expected_app
        ensure.assert_called_once_with("BookBuddy Backend", prompt=True)
        run.assert_called_once_with(
            expected_app, host="127.0.0.9", port=9123, log_level="warning", loop="asyncio", http="h11", ws="none", timeout_graceful_shutdown=17,
        )

    def test_provider_import_boundary(self):
        root = Path(__file__).resolve().parents[1]
        offenders = []
        for path in root.rglob("*.py"):
            if "venv" in path.parts or path.parts[-2:-1] == ("ai",) or path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8")
            if "from google" in text or "google.genai" in text:
                offenders.append(path.name)
        self.assertEqual([], offenders)

    def test_windows_sidecar_never_creates_a_console_window(self):
        source = Path(__file__).resolve().parents[1] / "frontend" / "src-tauri" / "src" / "lib.rs"
        source = source.read_text(encoding="utf-8")
        self.assertIn("CREATE_NO_WINDOW", source)
        self.assertIn("hide_console(&mut command)", source)

    def test_diagnostic_is_isolated_from_book_or_application_orchestration(self):
        source = (Path(__file__).resolve().parents[1] / "backend" / "gemini_test.py").read_text(encoding="utf-8")
        for forbidden in ("analysis_engine", "parse_epub", "BookDatabase", "ReplayCoordinator", "uvicorn"):
            self.assertNotIn(forbidden, source)


class TaskSupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_requests_cancellation_waits_and_flushes(self):
        with tempfile.TemporaryDirectory() as root:
            sessions = SessionManager(str(Path(root, "state.json")))
            supervisor = TaskSupervisor(sessions, 1)
            released = asyncio.Event()

            async def job():
                await released.wait()

            supervisor.submit("Book::session", job())
            released.set()
            await supervisor.shutdown()
            self.assertTrue(Path(root, "state.json").is_file())


if __name__ == "__main__":
    unittest.main()
