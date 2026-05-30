import os
import json
import time
import urllib.request
import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, List

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Таймаут сетевых вызовов (сек). Для urllib применяется как socket-таймаут на
# каждую блокирующую операцию чтения, поэтому для стриминга ограничивает паузу
# между чанками, а не общую длительность ответа. Переопределяется через env.
HTTP_TIMEOUT = float(os.environ.get("MATHESIS_HTTP_TIMEOUT", "60"))

# Ретраи на уровне менеджера: число ПОВТОРНЫХ попыток (всего попыток = retries + 1).
MODEL_MAX_RETRIES = int(os.environ.get("MATHESIS_MODEL_RETRIES", "2"))
# Базовая задержка экспоненциального backoff (сек): delay = base * 2**(attempt-1).
MODEL_RETRY_BASE_DELAY = float(os.environ.get("MATHESIS_MODEL_RETRY_DELAY", "1.0"))


class ModelError(RuntimeError):
    """Сбой обращения к модели (исчерпаны ретраи). Используется в strict-режиме,
    чтобы ошибки не «глотались» молчаливым возвратом пустой строки."""


class ModelTimeout(ModelError):
    """Превышен таймаут обращения к модели."""

def log_think(content: str):
    from pathlib import Path
    import datetime

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    logs_dir = PROJECT_ROOT / "logs" / "pipeline" / "think"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_path = logs_dir / f"{timestamp}.txt"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass


class ModelStrategy(ABC):
    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        self.model_name = model_name
        self.api_key = api_key

    @abstractmethod
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False, stream_callback=None) -> str:
        pass

    @abstractmethod
    def get_embedding(self, text: str) -> Optional[List[float]]:
        pass


class OllamaStrategy(ModelStrategy):
    def _get_base_url(self) -> str:
        # Check api_key (often used as host for Ollama in this codebase)
        if self.api_key and (self.api_key.startswith("http://") or self.api_key.startswith("https://")):
            return self.api_key.rstrip('/')

        # Check environment variable
        env_host = os.environ.get("MATHESIS_OLLAMA_HOST") or os.environ.get("MATHESIS_EMBED_API_KEY")
        if env_host and (env_host.startswith("http://") or env_host.startswith("https://")):
            return env_host.rstrip('/')

        return "http://localhost:11434"

    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False, stream_callback=None) -> str:
        model = self.model_name or "qwen2.5:14b"
        base_url = self._get_base_url()
        url = f"{base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream_callback is not None,
            "options": {
                "temperature": 0.6,
                "top_p": 0.9,
                "num_ctx": 8192,
                "num_predict": 8192,
                "repeat_penalty": 1.1,
                "repeat_last_n": 8192
            }
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                if stream_callback is not None:
                    full_ans = []
                    for line in response:
                        if line:
                            chunk_data = json.loads(line.decode("utf-8"))
                            chunk = chunk_data.get("response", "")
                            full_ans.append(chunk)
                            stream_callback(chunk)
                    ans = "".join(full_ans)
                else:
                    result = json.loads(response.read().decode("utf-8"))
                    ans = result.get("response", "")

                think_match = re.search(r'<think>(.*?)</think>', ans, re.DOTALL)
                if think_match:
                    log_think(think_match.group(1).strip())
                    ans = re.sub(r'<think>.*?</think>', '', ans, flags=re.DOTALL).strip()
                return ans
        except Exception as e:
            print(f"[OllamaStrategy] Error: {e} (URL: {url})")
            return ""

    def generate_with_images(self, prompt: str, images: list, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
        """Мультимодальный запрос к Ollama (vision/OCR): изображения кодируются в
        base64 и кладутся в поле `images` запроса /api/generate. Требует
        мультимодальной модели (llava/qwen-vl и т.п.)."""
        import base64
        model = self.model_name or "llava:latest"
        base_url = self._get_base_url()
        url = f"{base_url}/api/generate"
        encoded = [base64.b64encode(img).decode("ascii") for img in images]
        payload = {"model": model, "prompt": prompt, "stream": False, "images": encoded}
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result.get("response", "")
        except Exception as e:
            print(f"[OllamaStrategy] Vision error: {e} (URL: {url})")
            return ""

    def get_embedding(self, text: str) -> Optional[List[float]]:
        model = self.model_name or "nomic-embed-text:latest"
        base_url = self._get_base_url()
        url = f"{base_url}/api/embeddings"
        payload = {
            "model": model,
            "prompt": text
        }
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'))
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get("embedding")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ""
            print(f"[OllamaStrategy] Embedding error: HTTP {e.code} {e.reason} (URL: {url}) Body: {error_body}")

            # If 404 and we used /api/embeddings, maybe the endpoint is gone or model missing
            if e.code == 404 and "api/embeddings" in url and "model" not in error_body.lower():
                print("[OllamaStrategy] Retrying with /api/embed endpoint...")
                url = f"{base_url}/api/embed"
                payload = {"model": model, "input": text}
                try:
                    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'))
                    req.add_header('Content-Type', 'application/json')
                    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                        result = json.loads(response.read().decode('utf-8'))
                        # /api/embed returns {"embeddings": [[...]]}
                        return result.get("embeddings", [None])[0]
                except Exception as e2:
                    print(f"[OllamaStrategy] Embedding fallback error: {e2} (URL: {url})")
            return None
        except Exception as e:
            print(f"[OllamaStrategy] Embedding error: {e} (URL: {url})")
            return None


class GeminiStrategy(ModelStrategy):
    _last_request_time = 0.0
    _min_interval = 5.0  # Strict interval (max 12 RPM) to stay safely below 15 RPM

    def _enforce_rate_limit(self):
        current_time = time.time()
        elapsed = current_time - GeminiStrategy._last_request_time
        if elapsed < GeminiStrategy._min_interval:
            sleep_time = GeminiStrategy._min_interval - elapsed
            print(f"[GeminiStrategy] Rate limiting: sleeping for {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
        GeminiStrategy._last_request_time = time.time()

    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False, stream_callback=None) -> str:
        self._enforce_rate_limit()
        if not GEMINI_AVAILABLE:
            print("[GeminiStrategy] google-genai is not installed.")
            return ""

        api_key = self.api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("[GeminiStrategy] No GEMINI_API_KEY found.")
            return ""

        model = self.model_name or "gemini-3.1-flash-lite"
        client = genai.Client(api_key=api_key)

        config = types.GenerateContentConfig(
            temperature=0.0,
            system_instruction=system_prompt,
        )
        if json_mode:
            config.response_mime_type = "application/json"

        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            return response.text
        except Exception as e:
            print(f"[GeminiStrategy] Error: {e}")
            return ""

    def get_embedding(self, text: str) -> Optional[List[float]]:
        self._enforce_rate_limit()
        if not GEMINI_AVAILABLE:
            return None
        api_key = self.api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None

        model = self.model_name or "text-embedding-004"
        client = genai.Client(api_key=api_key)
        try:
            result = client.models.embed_content(
                model=model,
                contents=text
            )
            if isinstance(result.embeddings, list) and len(result.embeddings) > 0:
                return result.embeddings[0].values
            return None
        except Exception as e:
            print(f"[GeminiStrategy] Embedding error: {e}")
            return None


class OpenAIStrategy(ModelStrategy):
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False, stream_callback=None) -> str:
        if not OPENAI_AVAILABLE:
            print("[OpenAIStrategy] openai is not installed.")
            return ""

        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("[OpenAIStrategy] No OPENAI_API_KEY found.")
            return ""

        model = self.model_name or "gpt-4o-mini"
        client = openai.OpenAI(api_key=api_key)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": 0.0,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            print(f"[OpenAIStrategy] Error: {e}")
            return ""

    def get_embedding(self, text: str) -> Optional[List[float]]:
        if not OPENAI_AVAILABLE:
            return None
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None

        model = self.model_name or "text-embedding-3-small"
        client = openai.OpenAI(api_key=api_key)
        try:
            response = client.embeddings.create(
                input=[text],
                model=model
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"[OpenAIStrategy] Embedding error: {e}")
            return None


class GroqStrategy(ModelStrategy):
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False, stream_callback=None) -> str:
        if not OPENAI_AVAILABLE:
            print("[GroqStrategy] openai package is required for Groq.")
            return ""

        api_key = self.api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            print("[GroqStrategy] No GROQ_API_KEY found.")
            return ""

        model = self.model_name or "llama-3.3-70b-versatile"
        client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": 0.0,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            print(f"[GroqStrategy] Error: {e}")
            return ""

    def get_embedding(self, text: str) -> Optional[List[float]]:
        print("[GroqStrategy] Groq does not support embeddings.")
        return None


class LlamaCppStrategy(ModelStrategy):
    """
    Local execution of GGUF models using llama-cpp-python.
    If api_key is an HTTP URL, acts as a client to a local llama.cpp server.
    Otherwise, loads the .gguf model directly in memory.
    """
    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(model_name, api_key)
        self._llm = None

    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False, stream_callback=None) -> str:
        model = self.model_name
        if not model:
            print("[LlamaCppStrategy] Error: No model path provided.")
            return ""

        # If api_key is a URL, treat it as an OpenAI-compatible endpoint
        if self.api_key and (self.api_key.startswith("http://") or self.api_key.startswith("https://")):
            try:
                import openai
                client = openai.OpenAI(api_key="none", base_url=self.api_key)
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                kwargs = {"model": model, "messages": messages, "temperature": 0.0}
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                response = client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
            except Exception as e:
                print(f"[LlamaCppStrategy] Error (REST): {e}")
                return ""

        # Otherwise, run it directly in-process via llama_cpp
        try:
            from llama_cpp import Llama

            if self._llm is None or getattr(self, '_current_model', None) != model:
                print(f"[LlamaCppStrategy] Loading GGUF model in memory: {model}...")
                # Try to enable GPU if available (n_gpu_layers=-1)
                self._llm = Llama(model_path=model, n_ctx=4096, n_gpu_layers=-1, verbose=False)
                self._current_model = model

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            kwargs = {"messages": messages, "temperature": 0.0}
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            print("[LlamaCppStrategy] Inferencing locally...")
            response = self._llm.create_chat_completion(**kwargs)
            return response["choices"][0]["message"]["content"]

        except ImportError:
            print("[LlamaCppStrategy] Error: llama-cpp-python is not installed. Please `pip install llama-cpp-python`.")
            return ""
        except Exception as e:
            print(f"[LlamaCppStrategy] Error (Local): {e}")
            return ""

    def get_embedding(self, text: str) -> Optional[List[float]]:
        # For simplicity, fallback to failure or use embedding if llama_cpp model supports it
        return None

class ModelFactory:
    @staticmethod
    def create_strategy(provider: str, model_name: Optional[str] = None, api_key: Optional[str] = None) -> ModelStrategy:
        provider = provider.lower().strip()
        if provider == "gemini":
            return GeminiStrategy(model_name, api_key)
        elif provider == "openai":
            return OpenAIStrategy(model_name, api_key)
        elif provider == "groq":
            return GroqStrategy(model_name, api_key)
        elif provider == "llama_cpp":
            return LlamaCppStrategy(model_name, api_key)
        else:
            return OllamaStrategy(model_name, api_key)


class ModelManager:
    _instance = None

    def __init__(self):
        if ModelManager._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            self.strategies: Dict[str, ModelStrategy] = {}
            # Default to Ollama if nothing configured
            self.setup_role("main", "ollama")
            ModelManager._instance = self

    @staticmethod
    def get_instance():
        if ModelManager._instance is None:
            ModelManager()
        return ModelManager._instance

    def setup_role(self, role: str, provider: str, model_name: Optional[str] = None, api_key: Optional[str] = None):
        """Sets up a specific strategy for a given role (e.g. 'main', 'lean', 'preview')."""
        strategy = ModelFactory.create_strategy(provider, model_name, api_key)
        self.strategies[role] = strategy

    def _select_strategy(self, role: Optional[str], provider: Optional[str], model: Optional[str]) -> Optional[ModelStrategy]:
        if role and role in self.strategies:
            return self.strategies[role]
        if provider:
            return ModelFactory.create_strategy(provider, model)
        return self.strategies.get("main")

    def query_llm(self, prompt: str, model: Optional[str] = None, json_mode: bool = False, provider: Optional[str] = None, system_prompt: Optional[str] = None, role: Optional[str] = None, stream_callback=None, strict: bool = False, max_retries: Optional[int] = None) -> str:
        """Запрос к LLM с ретраями и экспоненциальным backoff.

        По умолчанию (`strict=False`) при исчерпании ретраев возвращает "" —
        обратная совместимость с существующими вызовами. При `strict=True`
        бросает ModelError, чтобы ошибка не «утонула» молча.

        Стриминг (stream_callback задан) не ретраится: повторная попытка
        отдала бы колбэку частичный вывод дважды.
        """
        strategy = self._select_strategy(role, provider, model)
        if strategy is None:
            if strict:
                raise ModelError("No model strategy configured")
            print("[ModelManager] query_llm: no strategy configured")
            return ""

        attempts = 1 if stream_callback is not None else (MODEL_MAX_RETRIES if max_retries is None else max_retries) + 1
        last_err: Optional[str] = None
        for attempt in range(1, attempts + 1):
            try:
                result = strategy.generate_content(prompt, system_prompt, json_mode, stream_callback=stream_callback)
                if result and result.strip():
                    return result
                last_err = "empty response"
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
            if attempt < attempts:
                delay = MODEL_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(f"[ModelManager] query_llm attempt {attempt}/{attempts} failed ({last_err}); retry in {delay:.1f}s")
                time.sleep(delay)

        if strict:
            raise ModelError(f"query_llm failed after {attempts} attempt(s): {last_err}")
        print(f"[ModelManager] query_llm failed after {attempts} attempt(s): {last_err}")
        return ""

    def query_vision(self, prompt: str, images: list, *, provider: Optional[str] = None,
                     model: Optional[str] = None, role: str = "cv", strict: bool = False,
                     max_retries: Optional[int] = None) -> str:
        """Мультимодальный (vision/OCR) запрос с ретраями. MVP: поддерживается
        только Ollama (роль 'cv'); другие провайдеры — позже по тому же интерфейсу."""
        strategy = self._select_strategy(role, provider, model)
        if strategy is None or not isinstance(strategy, OllamaStrategy):
            got = type(strategy).__name__ if strategy else "None"
            msg = f"query_vision: поддерживается только OllamaStrategy (получено {got})"
            if strict:
                raise ModelError(msg)
            print(f"[ModelManager] {msg}")
            return ""

        attempts = (MODEL_MAX_RETRIES if max_retries is None else max_retries) + 1
        last_err: Optional[str] = None
        for attempt in range(1, attempts + 1):
            try:
                result = strategy.generate_with_images(prompt, images)
                if result and result.strip():
                    return result
                last_err = "empty response"
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
            if attempt < attempts:
                time.sleep(MODEL_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
        if strict:
            raise ModelError(f"query_vision failed after {attempts} attempt(s): {last_err}")
        return ""

    def get_embedding(self, text: str, provider: Optional[str] = None, model: Optional[str] = None, role: Optional[str] = None, strict: bool = False, max_retries: Optional[int] = None) -> Optional[List[float]]:
        """Эмбеддинг с ретраями. По умолчанию возвращает None при сбое
        (обратная совместимость); при `strict=True` бросает ModelError."""
        strategy = self._select_strategy(role, provider, model)
        if strategy is None:
            if strict:
                raise ModelError("No model strategy configured")
            return None

        attempts = (MODEL_MAX_RETRIES if max_retries is None else max_retries) + 1
        last_err: Optional[str] = None
        for attempt in range(1, attempts + 1):
            try:
                emb = strategy.get_embedding(text)
                if emb:
                    return emb
                last_err = "empty embedding"
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
            if attempt < attempts:
                delay = MODEL_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(f"[ModelManager] get_embedding attempt {attempt}/{attempts} failed ({last_err}); retry in {delay:.1f}s")
                time.sleep(delay)

        if strict:
            raise ModelError(f"get_embedding failed after {attempts} attempt(s): {last_err}")
        return None
