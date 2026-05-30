"""Тесты централизованной загрузки .env (ключи провайдеров по умолчанию)."""
from __future__ import annotations

import importlib

from pipeline import config


def test_load_dotenv_populates_environ(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        'GEMINI_API_KEY=secret-gemini\n'
        '# комментарий\n'
        'OPENAI_API_KEY="quoted-openai"\n'
        '\n'
        "GROQ_API_KEY='single-quoted'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    config._load_dotenv()
    import os
    assert os.environ["GEMINI_API_KEY"] == "secret-gemini"
    assert os.environ["OPENAI_API_KEY"] == "quoted-openai"
    assert os.environ["GROQ_API_KEY"] == "single-quoted"


def test_existing_env_not_overwritten(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "already-set")
    config._load_dotenv()
    import os
    assert os.environ["GEMINI_API_KEY"] == "already-set"  # приоритет у реального env


def test_missing_env_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)  # .env отсутствует
    config._load_dotenv()  # не должно падать


def test_config_module_imports_cleanly():
    importlib.reload(config)  # повторный импорт с загрузкой .env не падает
    assert hasattr(config, "get_db_path")
