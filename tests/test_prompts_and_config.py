"""Тесты внешних промптов (4.3) и конфигурации (4.4)."""
from __future__ import annotations

from pipeline import prompts
from pipeline.prompts import load_prompt, render


def test_render_substitutes_double_braces():
    assert render("hello {{name}}", name="world") == "hello world"


def test_render_does_not_touch_latex_dollar_and_braces():
    # LaTeX-подобный текст с $ и одиночными {} не должен ломаться.
    tpl = r"$\frac{1}{2}$ for {{dep}} and \mathbb{R}"
    out = render(tpl, dep="X")
    assert out == r"$\frac{1}{2}$ for X and \mathbb{R}"


def test_render_keeps_unknown_placeholders():
    assert render("{{a}} {{b}}", a="1") == "1 {{b}}"


def test_macro_notation_prompt_loads_and_interpolates():
    out = load_prompt("macro_notation", dep="open interval")
    assert "open interval" in out
    assert "JSON" in out


def test_available_prompts_lists_macro_notation():
    assert "macro_notation" in prompts.available_prompts()


def test_api_config_cache_and_reload():
    from pipeline import config
    a = config._load_api_config()
    b = config._load_api_config()
    assert a is b  # lru_cache возвращает тот же объект
    config.reload_api_config()
    c = config._load_api_config()
    assert isinstance(c, dict)


def test_resolve_module_config_priority():
    from pipeline.config import resolve_module_config
    # глобальный аргумент важнее модульного
    provider, model, _ = resolve_module_config(
        "lean", global_provider="groq", module_provider="ollama",
        global_model="m-global", module_model="m-mod",
    )
    assert provider == "groq"
    assert model == "m-global"
