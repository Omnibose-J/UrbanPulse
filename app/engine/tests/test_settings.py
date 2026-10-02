"""ENGINE_ENV_FILE selects the env file. Values in this test are fixtures, not secrets."""

from engine import settings


def test_env_file_replaces_the_default_and_skip_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("ENGINE_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("ENGINE_ENV_FILE_PROBE", raising=False)
    named = tmp_path / "named.env"
    named.write_text("ENGINE_ENV_FILE_PROBE=from-named-file\n", encoding="utf-8")
    monkeypatch.setenv("ENGINE_ENV_FILE", str(named))
    assert settings.env_file() == named
    settings.load_env()
    loaded = settings.require(("ENGINE_ENV_FILE_PROBE",))
    assert loaded["ENGINE_ENV_FILE_PROBE"] == "from-named-file"
    monkeypatch.setenv("ENGINE_SKIP_DOTENV", "1")
    monkeypatch.delenv("ENGINE_ENV_FILE_PROBE")
    assert settings.env_file() is None
    settings.load_env()
    assert "ENGINE_ENV_FILE_PROBE" not in __import__("os").environ
