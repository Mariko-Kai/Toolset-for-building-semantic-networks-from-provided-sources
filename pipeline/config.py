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

import os
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Загружает .env (ключи провайдеров по умолчанию) в os.environ как можно
    раньше — до того, как стратегии моделей прочитают переменные окружения.

    Использует python-dotenv, если он установлен; иначе — простой встроенный
    парсер KEY=VALUE (чтобы .env работал и без зависимости). Существующие
    переменные окружения НЕ перезаписываются (setdefault).
    """
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)  # не перезаписывает уже заданные переменные
        return
    except ImportError:
        pass
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_dotenv()


# Единый источник истины для пути к канонической БД (ТЗ Этап 2.3).
# Переопределяется через переменную окружения MATHESIS_DB_PATH (полезно для тестов/CI).
def get_db_path() -> str:
    return os.environ.get("MATHESIS_DB_PATH") or str(PROJECT_ROOT / "db" / "mathesis_index.db")


def get_subprocess_timeout() -> float:
    """Wall-clock ceiling (seconds) for external subprocess steps — pdflatex, the
    enrichment extract/align/synth children, and the final book build. No external
    call may hang forever (ТЗ: «границы и таймауты на всё внешнее»).
    Override via MATHESIS_SUBPROCESS_TIMEOUT (default 900s)."""
    try:
        return float(os.environ.get("MATHESIS_SUBPROCESS_TIMEOUT", "900"))
    except (TypeError, ValueError):
        return 900.0


def resolve_gguf_path(model: str):
    """Finds the reranker GGUF file by name/path from config. Searches: as-is;
    relative to PROJECT_ROOT; in PROJECT_ROOT/llama; in $MATHESIS_LLAMA_DIR.
    Returns a Path or None. (Was duplicated in enrichment_coordinator/ensemble_extractor.)"""
    if not model or not str(model).lower().endswith(".gguf"):
        return None
    candidates = [Path(model), PROJECT_ROOT / model, PROJECT_ROOT / "llama" / Path(model).name]
    extra_dir = os.environ.get("MATHESIS_LLAMA_DIR")
    if extra_dir:
        candidates.append(Path(extra_dir) / Path(model).name)
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


PROVIDERS = ["ollama", "gemini", "openai", "groq", "hf", "llama_cpp"]

# Дефолтные модели для каждого провайдера
_MODELS = {
    "ollama": os.environ.get("MATHESIS_OLLAMA_MODEL") or os.environ.get("MATHESIS_DEFAULT_OLLAMA_MODEL") or "qwen3:8b",
    "gemini": os.environ.get("MATHESIS_GEMINI_MODEL") or os.environ.get("MATHESIS_DEFAULT_GEMINI_MODEL") or "gemini-2.5-flash",
    "openai": os.environ.get("MATHESIS_OPENAI_MODEL") or os.environ.get("MATHESIS_DEFAULT_OPENAI_MODEL") or "gpt-4o-mini",
    "groq":   os.environ.get("MATHESIS_GROQ_MODEL") or os.environ.get("MATHESIS_DEFAULT_GROQ_MODEL") or "llama-3.3-70b-versatile",
    "hf":     os.environ.get("MATHESIS_HF_MODEL") or "Qwen/Qwen2.5-Coder-Artifacts",
    "llama_cpp": os.environ.get("MATHESIS_LLAMA_CPP_MODEL") or "bge-reranker-v2-m3-Q6_K.gguf",
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
    "embed": {
        # Embedding model defaults per provider
        "ollama": "nomic-embed-text:latest",
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
    "embed": {
        "provider": "ollama",
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
      3. Переменная окружения (MATHESIS_{MODULE}_PROVIDER / MATHESIS_{MODULE}_MODEL / MATHESIS_{MODULE}_API_KEY)
      4. Дефолт из config.py

    Returns:
        (provider, model, api_key)
    """
    # Load env-level overrides
    env_provider = os.environ.get(f"MATHESIS_{module.upper()}_PROVIDER")
    env_model = os.environ.get(f"MATHESIS_{module.upper()}_MODEL")
    env_api_key = os.environ.get(f"MATHESIS_{module.upper()}_API_KEY")

    # 1. Провайдер: CLI global > CLI module > ENV module > hardcoded default
    provider = global_provider or module_provider or env_provider or get_default_provider(module)

    # 2. Модель: CLI global > CLI module > ENV module > default for provider
    if global_model:
        model = global_model
    elif module_model:
        model = module_model
    elif env_model:
        model = env_model
    else:
        model = get_default_model(module, provider)

    # 3. API ключ: CLI global > CLI module > ENV module > ENV provider default
    env_provider_default_api_key = None
    if provider == "gemini":
        env_provider_default_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    elif provider == "openai":
        env_provider_default_api_key = os.environ.get("OPENAI_API_KEY")
    elif provider == "groq":
        env_provider_default_api_key = os.environ.get("GROQ_API_KEY")

    api_key = global_api_key or module_api_key or env_api_key or env_provider_default_api_key

    return provider, model, api_key

