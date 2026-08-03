import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from ai_credentials import EncryptedCredentialStore
from ai.models import PermanentAIError, ProviderResponse
from ai_settings_state import AISettingsStateStore
from app import create_app
from config import load_config


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="DPAPI is Windows-only")
def test_credentials_are_encrypted_for_the_windows_user(tmp_path):
    path = tmp_path / "ai-credentials.bin"
    store = EncryptedCredentialStore(path)
    text_key = "text-secret-that-must-not-be-visible"
    vision_key = "vision-secret-that-must-not-be-visible"

    store.write([text_key], [vision_key])

    raw = path.read_bytes()
    assert text_key.encode() not in raw
    assert vision_key.encode() not in raw
    assert store.read() == {"api_keys": [text_key], "vision_api_keys": [vision_key]}


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="DPAPI is Windows-only")
def test_encrypted_settings_override_dotenv_without_exposing_values(tmp_path):
    config_dir = tmp_path / "private-config"
    EncryptedCredentialStore(config_dir / "ai-credentials.bin").write(
        ["stored-text-secret-value"], ["stored-vision-secret-value"]
    )
    (tmp_path / ".env").write_text(
        "GEMINI_API_KEY=dotenv-secret-value\nGEMINI_VISION_API_KEY=dotenv-vision-value\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path, {"BOOKBUDDY_CONFIG_DIR": str(config_dir)})

    assert config.ai.credential_source == "encrypted"
    assert [value for _, value in config.ai.api_keys] == ["stored-text-secret-value"]
    assert [value for _, value in config.ai.vision_api_keys] == ["stored-vision-secret-value"]
    assert "stored-text-secret-value" not in repr(config)


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="DPAPI is Windows-only")
def test_ai_settings_api_returns_status_but_never_secrets(tmp_path):
    config = load_config(tmp_path, {
        "BOOKBUDDY_LIBRARY_DIR": str(tmp_path / "library"),
        "BOOKBUDDY_CACHE_DIR": str(tmp_path / "cache"),
        "BOOKBUDDY_LOG_DIR": str(tmp_path / "logs"),
        "BOOKBUDDY_CONFIG_DIR": str(tmp_path / "config"),
    })
    secret = "api-secret-that-must-never-be-returned"
    with TestClient(create_app(config)) as client:
        response = client.put("/settings/ai", json={"api_keys": [secret], "vision_api_keys": []})
        assert response.status_code == 200
        payload = response.json()
        assert payload["configured"] is True
        assert payload["key_count"] == 1
        assert payload["source"] == "encrypted"
        assert secret not in response.text
        assert secret not in client.get("/settings/ai").text
    assert secret.encode() not in (tmp_path / "config" / "ai-credentials.bin").read_bytes()


def test_non_secret_ai_state_is_atomic_and_defaults_to_opt_out(tmp_path):
    store = AISettingsStateStore(tmp_path / "ai-settings-state.json")
    assert store.read()["background_analysis_enabled"] is False
    store.update(background_analysis_enabled=True)
    record = store.record_verification("text", "success", "gemini-test", "Connected successfully.")
    assert record["background_analysis_enabled"] is True
    assert store.read()["verification"]["text"]["outcome"] == "success"
    assert not Path(str(store.path) + ".tmp").exists()


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="DPAPI is Windows-only")
def test_partial_ai_settings_updates_preserve_omitted_key_pool(tmp_path):
    config = load_config(tmp_path, {
        "BOOKBUDDY_LIBRARY_DIR": str(tmp_path / "library"),
        "BOOKBUDDY_CACHE_DIR": str(tmp_path / "cache"),
        "BOOKBUDDY_LOG_DIR": str(tmp_path / "logs"),
        "BOOKBUDDY_CONFIG_DIR": str(tmp_path / "config"),
    })
    with TestClient(create_app(config)) as client:
        assert client.put("/settings/ai", json={"api_keys": ["first-text-secret-value"], "vision_api_keys": ["first-vision-secret-value"]}).status_code == 200
        response = client.patch("/settings/ai", json={"api_keys": ["replacement-text-secret-value"]})
        assert response.status_code == 200
        payload = response.json()
        assert payload["key_count"] == 1
        assert payload["vision_key_count"] == 1
        assert "replacement-text-secret-value" not in response.text
        assert "first-vision-secret-value" not in response.text
    stored = EncryptedCredentialStore(tmp_path / "config" / "ai-credentials.bin").read()
    assert stored == {"api_keys": ["replacement-text-secret-value"], "vision_api_keys": ["first-vision-secret-value"]}


class _VerificationProvider:
    name = "gemini"
    def __init__(self, error=None): self.error = error
    def is_available(self, capability): return True
    def verify(self, capability, *, model):
        if self.error: raise self.error
        return ProviderResponse(provider=self.name, model=model, credential_id="redacted-id")
    def close(self): pass


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="DPAPI is Windows-only")
def test_verification_returns_sanitized_stable_outcomes(tmp_path):
    import app as app_module
    config = load_config(tmp_path, {
        "BOOKBUDDY_LIBRARY_DIR": str(tmp_path / "library"),
        "BOOKBUDDY_CACHE_DIR": str(tmp_path / "cache"),
        "BOOKBUDDY_LOG_DIR": str(tmp_path / "logs"),
        "BOOKBUDDY_CONFIG_DIR": str(tmp_path / "config"),
    })
    with TestClient(create_app(config)) as client:
        app_module.ai_manager.provider = _VerificationProvider()
        response = client.post("/settings/ai/verify", json={"capability": "text"})
        assert response.status_code == 200
        assert response.json()["outcome"] == "success"
        assert response.json()["timestamp"] == response.json()["verified_at"]
        app_module.ai_manager.provider = _VerificationProvider(PermanentAIError("raw secret provider payload", code="invalid_key"))
        response = client.post("/settings/ai/verify", json={"capability": "text"})
        assert response.json()["outcome"] == "invalid_key"
        assert "raw secret provider payload" not in response.text
