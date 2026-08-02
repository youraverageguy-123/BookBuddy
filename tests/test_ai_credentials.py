import pytest
from fastapi.testclient import TestClient

from ai_credentials import EncryptedCredentialStore
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
