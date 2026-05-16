"""
pipeline/config.py — Централизованная конфигурация провайдеров для Mathesis Pipeline.

Структура:
  PROVIDERS       — список допустимых провайдеров.
  DEFAULTS        — дефолтный провайдер и дефолтная модель для каждого провайдера,
                    отдельно для каждого модуля: extract, synth, lean.

Приоритет конфигурации (выше — важнее):
  1. Явный глобальный --model/--provider/--api-key (оверрайдит все модули)
  2. Модульный --extract-model, --synth-model, --lean-model
  3. Дефолты из этого файла
"""

PROVIDERS = ["ollama", "gemini", "openai", "groq", "hf"]

# Дефолтные модели для каждого провайдера
_MODELS = {
    "ollama": "qwen3:8b",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "groq":   "llama-3.3-70b-versatile",
    "hf":     "Qwen/Qwen2.5-Coder-Artifacts",
}

# Переопределения модели по умолчанию для конкретных модулей и провайдеров
# (если модуль требует другую модель по умолчанию, чем остальные)
_MODULE_MODEL_OVERRIDES = {
    "lean": {
        "groq":   "openai/gpt-oss-120b",   # Лучшая модель Groq для Lean-кода
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4o",                  # Lean требует более мощной модели
    },
    "synth": {
        "groq":   "llama-3.3-70b-versatile",
        "gemini": "gemini-2.5-flash",
    },
    "extract": {
        # Для извлечения подходят быстрые и дешёвые модели
        "groq":   "llama-3.3-70b-versatile",
        "gemini": "gemini-2.5-flash",
    },
}

DEFAULTS = {
    "extract": {
        "provider": "ollama",
    },
    "synth": {
        "provider": "ollama",
    },
    "lean": {
        "provider": "ollama",  # Если lean-provider не указан, используется основной
    },
}


def get_default_model(module: str, provider: str) -> str:
    """Возвращает дефолтную модель для данного модуля и провайдера."""
    overrides = _MODULE_MODEL_OVERRIDES.get(module, {})
    return overrides.get(provider, _MODELS.get(provider, "qwen3:8b"))


def get_default_provider(module: str) -> str:
    """Возвращает дефолтный провайдер для данного модуля."""
    return DEFAULTS.get(module, {}).get("provider", "ollama")


def resolve_module_config(
    module: str,
    global_provider: str | None = None,
    global_model: str | None = None,
    global_api_key: str | None = None,
    module_provider: str | None = None,
    module_model: str | None = None,
    module_api_key: str | None = None,
) -> tuple[str, str, str | None]:
    """
    Разрешает итоговые (provider, model, api_key) для модуля с учётом приоритетов.

    Приоритет:
      1. Глобальный аргумент (--provider / --model / --api-key)
      2. Модульный аргумент (--extract-* / --synth-* / --lean-*)
      3. Дефолт из config.py

    Returns:
        (provider, model, api_key)
    """
    # 1. Провайдер
    provider = global_provider or module_provider or get_default_provider(module)

    # 2. Модель: глобальная > модульная > дефолт для данного провайдера
    if global_model:
        model = global_model
    elif module_model:
        model = module_model
    else:
        model = get_default_model(module, provider)

    # 3. API ключ
    api_key = global_api_key or module_api_key

    return provider, model, api_key
