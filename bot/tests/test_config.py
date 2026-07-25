import pytest

from app.config import ConfigurationError, Settings


def test_loads_configuration(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("BOT_BACKEND_BASE_URL", "https://api.example/")
    monkeypatch.setenv("BOT_API_TIMEOUT", "2.5")
    monkeypatch.setenv("BOT_DEFAULT_LANGUAGE", "ru")
    settings = Settings.from_env()
    assert settings.backend_base_url == "https://api.example"
    assert settings.api_timeout == 2.5
    assert settings.default_language == "ru"


@pytest.mark.parametrize("missing", ["BOT_TOKEN", "BOT_BACKEND_BASE_URL"])
def test_required_configuration_fails_clearly(monkeypatch, missing):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("BOT_BACKEND_BASE_URL", "https://api.example")
    monkeypatch.delenv(missing)
    with pytest.raises(ConfigurationError, match=missing):
        Settings.from_env()


@pytest.mark.parametrize("timeout", ["invalid", "0", "-1"])
def test_invalid_timeout_fails_clearly(monkeypatch, timeout):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("BOT_BACKEND_BASE_URL", "https://api.example")
    monkeypatch.setenv("BOT_API_TIMEOUT", timeout)
    with pytest.raises(ConfigurationError, match="BOT_API_TIMEOUT"):
        Settings.from_env()
