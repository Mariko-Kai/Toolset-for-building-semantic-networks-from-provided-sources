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

PROVIDERS = ["ollama", "gemini", "openai", "groq", "hf", "llama_cpp"]

# Дефолтные модели для каждого провайдера
_MODELS = {
    "ollama": "qwen3:8b",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "groq":   "llama-3.3-70b-versatile",
    "hf":     "Qwen/Qwen2.5-Coder-Artifacts",
    "llama_cpp": "bge-reranker-v2-m3-Q6_K.gguf",
}

# Переопределения модели по умолчанию для конкретных модулей и провайдеров
# (если модуль требует другую модель по умолчанию, чем остальные)
_MODULE_MODEL_OVERRIDES = {
    "lean": {
        "ollama": "goedel:latest",
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
    "preview": {
        # Модель предпросмотра — быстрая и лёгкая для сканирования всех страниц
        "ollama": "phi4-mini:latest",
        "groq":   "llama-3.1-8b-instant",
        "gemini": "gemini-2.5-flash-lite",
        "llama_cpp": "bge-reranker-v2-m3-Q6_K.gguf",
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
    "preview": {
        "provider": "llama_cpp",  # Модель предпросмотра по умолчанию использует llama_cpp (cross-encoder bge-reranker)
    },
}


def get_default_model(module: str, provider: str) -> str:
    """Возвращает дефолтную модель для данного модуля и провайдера."""
    overrides = _MODULE_MODEL_OVERRIDES.get(module, {})
    return overrides.get(provider, _MODELS.get(provider, "qwen3:8b"))


def get_default_provider(module: str) -> str:
    """Возвращает дефолтный провайдер для данного модуля."""
    return DEFAULTS.get(module, {}).get("provider", "ollama")


def _load_api_config():
    """Load api_config.json from the project root (cached)."""
    if hasattr(_load_api_config, '_cache'):
        return _load_api_config._cache
    import json
    from pathlib import Path
    config_path = Path(__file__).resolve().parent.parent / "api_config.json"
    try:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                _load_api_config._cache = json.load(f)
                return _load_api_config._cache
    except Exception:
        pass
    _load_api_config._cache = {}
    return _load_api_config._cache


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
      3. api_config.json (providers / models / api_keys секции)
      4. Дефолт из config.py

    Returns:
        (provider, model, api_key)
    """
    # Load api_config.json settings
    api_cfg = _load_api_config()
    cfg_provider = api_cfg.get("providers", {}).get(module)
    cfg_model = api_cfg.get("models", {}).get(module)

    # 1. Провайдер: CLI global > CLI module > api_config.json > hardcoded default
    provider = global_provider or module_provider or cfg_provider or get_default_provider(module)

    # 2. Модель: CLI global > CLI module > api_config.json > default for provider
    if global_model:
        model = global_model
    elif module_model:
        model = module_model
    elif cfg_model:
        model = cfg_model
    else:
        model = get_default_model(module, provider)

    # 3. API ключ: CLI global > CLI module > api_config.json for resolved provider
    cfg_api_key = api_cfg.get("api_keys", {}).get(provider)
    api_key = global_api_key or module_api_key or cfg_api_key

    return provider, model, api_key

