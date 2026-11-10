import tempfile
import unittest

from fastapi.testclient import TestClient

from ai.models import PermanentAIError
from ai_settings_state import AISettingsStateStore
from app import create_app
from config import load_config


class _ListingProvider:
    name = "gemini"

    def __init__(self, error=None):
        self.error = error

    def is_available(self, capability):
        return True

    def list_models(self, capability):
        if self.error:
            raise self.error
        return [
            {"id": "gemini-test-pro", "name": "Gemini Test Pro", "description": "Slow and careful."},
            {"id": "gemini-test-flash", "name": "Gemini Test Flash", "description": "Fast."},
        ]

    def close(self):
        pass


class AIModelSelectionTests(unittest.TestCase):
    def config(self, root):
        return load_config(root, {
            "BOOKBUDDY_LIBRARY_DIR": "library", "BOOKBUDDY_CACHE_DIR": "cache", "BOOKBUDDY_LOG_DIR": "logs",
            "BOOKBUDDY_CONFIG_DIR": "config", "GEMINI_MODEL_NAME": "gemini-from-env",
        })

    def test_models_are_listed_selected_and_remembered(self):
        import app as app_module
        with tempfile.TemporaryDirectory() as root:
            config = self.config(root)
            self.assertEqual("gemini-from-env", config.ai.chapter_model)
            with TestClient(create_app(config)) as client:
                app_module.ai_manager.provider = _ListingProvider()
                listed = client.get("/settings/ai/models").json()
                self.assertEqual("bookbuddy_ai_models_v1", listed["schema_version"])
                self.assertEqual("ok", listed["status"])
                self.assertEqual("gemini-from-env", listed["selected"])
                self.assertEqual(["gemini-test-pro", "gemini-test-flash"], [item["id"] for item in listed["models"]])

                app_module.ai_manager.provider = _ListingProvider(PermanentAIError("raw provider text", code="invalid_key"))
                failed = client.get("/settings/ai/models")
                self.assertEqual(200, failed.status_code)
                self.assertEqual("invalid_key", failed.json()["status"])
                self.assertEqual([], failed.json()["models"])
                self.assertNotIn("raw provider text", failed.text)

                self.assertEqual(422, client.patch("/settings/ai", json={"model": "bad model; rm -rf"}).status_code)
                chosen = client.patch("/settings/ai", json={"model": "gemini-test-pro"})
                self.assertEqual(200, chosen.status_code, chosen.text)
                self.assertEqual(
                    {"text": "gemini-test-pro", "dictionary": "gemini-test-pro", "vision": "gemini-test-pro"},
                    chosen.json()["models"],
                )
                self.assertEqual("gemini-test-pro", app_module.ai_manager.config.chapter_model)
                self.assertEqual("gemini-test-pro", client.get("/settings/ai/models").json()["selected"])

            stored = AISettingsStateStore(config.paths.config_dir / "ai-settings-state.json").read()
            self.assertEqual("gemini-test-pro", stored["models"]["text"])
            # The choice survives a restart and wins over the environment default.
            self.assertEqual("gemini-test-pro", self.config(root).ai.chapter_model)

    def test_state_store_ignores_malformed_model_entries(self):
        with tempfile.TemporaryDirectory() as root:
            store = AISettingsStateStore(f"{root}/state.json")
            store.update(models={"text": "  gemini-x  ", "vision": 7, "other": "nope"}, background_analysis_enabled=True)
            state = store.read()
            self.assertEqual({"text": "gemini-x"}, state["models"])
            self.assertTrue(state["background_analysis_enabled"])


if __name__ == "__main__":
    unittest.main()
