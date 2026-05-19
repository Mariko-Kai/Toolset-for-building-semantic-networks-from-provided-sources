"""
Export to Lean v2 — LLM-Assisted Translation
=============================================
Translates LaTeX entities to valid Lean 4 code using LLM.
Supports two providers: local Ollama and Google Gemini API.
Falls back to regex-based translation if LLM is unavailable.
Supports incremental validation (saves validated files individually).
"""
import sqlite3
import re
import os
import json
import urllib.request
import time
from pathlib import Path
from collections import defaultdict, deque

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

try:
    from gradio_client import Client as GradioClient
    GRADIO_AVAILABLE = True
except ImportError:
    GRADIO_AVAILABLE = False

try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except Exception:
    LLAMA_CPP_AVAILABLE = False

import datetime
from pipeline.lean_validator import validate_entity
PROJECT_ROOT = Path(__file__).resolve().parent.parent

def log_to_file(category: str, content: str, entity_id: str = None, attempt: int = None):
    """
    Saves content into a log file in logs/<category>/...
    And also appends to logs/pipeline_realtime.log in real-time with immediate disk flush.
    """
    import os
    import sys
    try:
        logs_dir = PROJECT_ROOT / "logs" / category
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # 1. Write the individual category log file
        parts = [timestamp]
        if entity_id:
            safe_eid = "".join(c for c in str(entity_id) if c.isalnum() or c in "-_")
            parts.append(safe_eid)
        if attempt is not None:
            parts.append(f"attempt_{attempt}")
            
        filename = "_".join(parts) + ".txt"
        file_path = logs_dir / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
                
        # 2. Append to the real-time unified streaming log file
        realtime_log = PROJECT_ROOT / "logs" / "pipeline_realtime.log"
        header = f"\n=== [{datetime.datetime.now().isoformat()}] CATEGORY: {category.upper()} | ENTITY: {entity_id} | ATTEMPT: {attempt} ===\n"
        with open(realtime_log, "a", encoding="utf-8") as f:
            f.write(header)
            f.write(content)
            f.write("\n" + "="*80 + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
                
        # 3. Flush standard output buffers for instant console response
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception as e:
        print(f"  [logging-error] Failed to write log to category {category}: {e}")
        sys.stdout.flush()

DB_PATH = PROJECT_ROOT / "mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"
LEAN_DIR = PROJECT_ROOT / "lean_validator"
VALIDATED_DIR = LEAN_DIR / "Validated"
OUT_FILE = LEAN_DIR / "MathesisGraph.lean"
SUCCESS_FILE = LEAN_DIR / "SuccessfulEntities.lean"

# Active LLM provider config (set by main() or setup_provider())
_LLM_PROVIDER = "ollama"  
_OLLAMA_MODEL = None
_GEMINI_CLIENT = None
_GEMINI_MODEL_NAME = None
_OPENAI_CLIENT = None
_OPENAI_MODEL_NAME = None
_GROQ_CLIENT = None
_GROQ_MODEL_NAME = None
_HF_CLIENT = None
_HF_MODEL_NAME = None
_LLAMA_CPP_CLIENT = None
_LLAMA_CPP_MODEL = None
_PREVIEW_LLAMA_CPP_CLIENT = None
_PREVIEW_LLAMA_CPP_MODEL = None
_LEAN_LLAMA_CPP_CLIENT = None
_LEAN_LLAMA_CPP_MODEL = None
# Suppress repeated llama.cpp "not initialized" warnings (print only once per run)
_LLAMA_CPP_WARNED = False

# Secondary (Lean) provider config
_LEAN_PROVIDER = None # If None, use _LLM_PROVIDER
_LEAN_GEMINI_CLIENT = None
_LEAN_GEMINI_MODEL = None
_LEAN_OPENAI_CLIENT = None
_LEAN_OPENAI_MODEL = None
_LEAN_GROQ_CLIENT = None
_LEAN_GROQ_MODEL = None
_LEAN_OLLAMA_MODEL = None
_LEAN_HF_CLIENT = None
_LEAN_HF_MODEL = None


def setup_provider(provider, api_key=None, model=None):
    """External setup for other modules to configure LLM provider."""
    global _LLM_PROVIDER, _OLLAMA_MODEL, _GEMINI_CLIENT, _GEMINI_MODEL_NAME, _OPENAI_CLIENT, _OPENAI_MODEL_NAME, _GROQ_CLIENT, _GROQ_MODEL_NAME, _HF_CLIENT, _HF_MODEL_NAME, _LLAMA_CPP_CLIENT, _LLAMA_CPP_MODEL
    _LLM_PROVIDER = provider
    
    if _LLM_PROVIDER == "gemini":
        if not GEMINI_AVAILABLE:
            print("ERROR: google-genai not installed.")
            return
        _GEMINI_CLIENT = genai.Client(api_key=api_key) if api_key else genai.Client()
        if model: _GEMINI_MODEL_NAME = model
    elif _LLM_PROVIDER == "openai":
        if not OPENAI_AVAILABLE:
            print("ERROR: openai not installed.")
            return
        active_key = api_key or os.environ.get("OPENAI_API_KEY") or "none"
        _OPENAI_CLIENT = openai.OpenAI(api_key=active_key)
        if model: _OPENAI_MODEL_NAME = model
    elif _LLM_PROVIDER == "groq":
        if not OPENAI_AVAILABLE:
            print("ERROR: openai/groq compatible SDK not installed.")
            return
        active_key = api_key or os.environ.get("GROQ_API_KEY") or "none"
        _GROQ_CLIENT = openai.OpenAI(api_key=active_key, base_url="https://api.groq.com/openai/v1")
        if model: _GROQ_MODEL_NAME = model
    elif _LLM_PROVIDER == "hf":
        if not GRADIO_AVAILABLE:
            print("  [lean-export] ERROR: gradio_client not installed. Run: pip install gradio_client")
            return
        _HF_CLIENT = GradioClient(model, token=api_key) if api_key else GradioClient(model)
        if model: _HF_MODEL_NAME = model
    elif _LLM_PROVIDER == "llama_cpp":
        if not LLAMA_CPP_AVAILABLE:
            print("  [lean-export] ERROR: llama-cpp-python not installed. Run: pip install llama-cpp-python")
            return
        try:
            if model:
                _LLAMA_CPP_CLIENT = Llama(model_path=model)
                _LLAMA_CPP_MODEL = model
            else:
                _LLAMA_CPP_MODEL = model
        except Exception as e:
            print(f"  [lean-export] ERROR initializing llama.cpp client: {e}")
            return
    elif _LLM_PROVIDER == "ollama":
        if model: _OLLAMA_MODEL = model

def setup_lean_provider(provider, api_key=None, model=None):
    """Configure a separate provider for Lean generation."""
    global _LEAN_PROVIDER, _LEAN_GEMINI_CLIENT, _LEAN_GEMINI_MODEL, _LEAN_OPENAI_CLIENT, _LEAN_OPENAI_MODEL, _LEAN_GROQ_CLIENT, _LEAN_GROQ_MODEL, _LEAN_OLLAMA_MODEL, _LEAN_HF_CLIENT, _LEAN_HF_MODEL, _LEAN_LLAMA_CPP_CLIENT, _LEAN_LLAMA_CPP_MODEL
    _LEAN_PROVIDER = provider
    
    if _LEAN_PROVIDER == "gemini":
        _LEAN_GEMINI_CLIENT = genai.Client(api_key=api_key) if api_key else genai.Client()
        _LEAN_GEMINI_MODEL = model
    elif _LEAN_PROVIDER == "openai":
        active_key = api_key or os.environ.get("OPENAI_API_KEY") or "none"
        _LEAN_OPENAI_CLIENT = openai.OpenAI(api_key=active_key)
        _LEAN_OPENAI_MODEL = model
    elif _LEAN_PROVIDER == "groq":
        active_key = api_key or os.environ.get("GROQ_API_KEY") or "none"
        _LEAN_GROQ_CLIENT = openai.OpenAI(api_key=active_key, base_url="https://api.groq.com/openai/v1")
        _LEAN_GROQ_MODEL = model
    elif _LEAN_PROVIDER == "ollama":
        _LEAN_OLLAMA_MODEL = model
    elif _LEAN_PROVIDER == "llama_cpp":
        if not LLAMA_CPP_AVAILABLE:
            print("  [lean-export] ERROR: llama-cpp-python not installed. Run: pip install llama-cpp-python")
            return
        try:
            if model:
                _LEAN_LLAMA_CPP_CLIENT = Llama(model_path=model)
                _LEAN_LLAMA_CPP_MODEL = model
            else:
                _LEAN_LLAMA_CPP_MODEL = model
            print(f"  [lean-export] Initialized local llama.cpp client for Lean provider: {model}")
        except Exception as e:
            print(f"  [lean-export] ERROR initializing llama.cpp client for lean provider: {e}")
    elif _LEAN_PROVIDER == "hf":
        if not GRADIO_AVAILABLE:
            print("  [lean-export] ERROR: gradio_client not installed. Run: pip install gradio_client")
            return
        _LEAN_HF_CLIENT = GradioClient(model, token=api_key) if api_key else GradioClient(model)
        if model: _LEAN_HF_MODEL = model


def setup_preview_provider(provider, api_key=None, model=None):
    """Configure a separate provider for preview (fast page scanning)."""
    global _PREVIEW_PROVIDER, _PREVIEW_GEMINI_CLIENT, _PREVIEW_GEMINI_MODEL, _PREVIEW_OPENAI_CLIENT, _PREVIEW_OPENAI_MODEL, _PREVIEW_GROQ_CLIENT, _PREVIEW_GROQ_MODEL, _PREVIEW_OLLAMA_MODEL, _PREVIEW_HF_CLIENT, _PREVIEW_HF_MODEL, _PREVIEW_LLAMA_CPP_CLIENT, _PREVIEW_LLAMA_CPP_MODEL
    # Initialize globals if not defined
    try:
        _ = _PREVIEW_PROVIDER
    except NameError:
        _PREVIEW_PROVIDER = None
        _PREVIEW_GEMINI_CLIENT = None
        _PREVIEW_GEMINI_MODEL = None
        _PREVIEW_OPENAI_CLIENT = None
        _PREVIEW_OPENAI_MODEL = None
        _PREVIEW_GROQ_CLIENT = None
        _PREVIEW_GROQ_MODEL = None
        _PREVIEW_OLLAMA_MODEL = None
        _PREVIEW_HF_CLIENT = None
        _PREVIEW_HF_MODEL = None
        _PREVIEW_LLAMA_CPP_CLIENT = None
        _PREVIEW_LLAMA_CPP_MODEL = None

    _PREVIEW_PROVIDER = provider
    if _PREVIEW_PROVIDER == "gemini":
        _PREVIEW_GEMINI_CLIENT = genai.Client(api_key=api_key) if api_key else genai.Client()
        _PREVIEW_GEMINI_MODEL = model
    elif _PREVIEW_PROVIDER == "openai":
        active_key = api_key or os.environ.get("OPENAI_API_KEY") or "none"
        _PREVIEW_OPENAI_CLIENT = openai.OpenAI(api_key=active_key)
        _PREVIEW_OPENAI_MODEL = model
    elif _PREVIEW_PROVIDER == "groq":
        active_key = api_key or os.environ.get("GROQ_API_KEY") or "none"
        _PREVIEW_GROQ_CLIENT = openai.OpenAI(api_key=active_key, base_url="https://api.groq.com/openai/v1")
        _PREVIEW_GROQ_MODEL = model
    elif _PREVIEW_PROVIDER == "ollama":
        _PREVIEW_OLLAMA_MODEL = model
    elif _PREVIEW_PROVIDER == "llama_cpp":
        if not LLAMA_CPP_AVAILABLE:
            print("  [lean-export] ERROR: llama-cpp-python not installed. Run: pip install llama-cpp-python")
            return
        try:
            _PREVIEW_LLAMA_CPP_CLIENT = Llama(model_path=model) if model else None
            _PREVIEW_LLAMA_CPP_MODEL = model
            print(f"  [lean-export] Initialized local llama.cpp client for Preview provider: {model}")
        except Exception as e:
            print(f"  [lean-export] ERROR initializing preview llama.cpp client: {e}")
    elif _PREVIEW_PROVIDER == "hf":
        if not GRADIO_AVAILABLE:
            print("  [lean-export] ERROR: gradio_client not installed. Run: pip install gradio_client")
            return
        _PREVIEW_HF_CLIENT = GradioClient(model, token=api_key) if api_key else GradioClient(model)
        if model: _PREVIEW_HF_MODEL = model



# ── Ollama Interface ─────────────────────────────────────────────────────────

def query_ollama(prompt, model="goedel:latest", system_prompt=None, json_mode=False):
    if not model:
        from pipeline.config import get_default_model
        model = get_default_model("extract", "ollama")
    url = "http://localhost:11434/api/generate"
    
    # Configure Ollama options dynamically:
    # Goedel-Formalizer requires large context, high prediction limit, and custom sampling.
    options = {
        "num_ctx": 8192,
        "num_predict": 2048,  # Increased default to prevent truncation
        "temperature": 0.0,
    }
    
    if "goedel" in model.lower() and "prover" not in model.lower():
        options["num_ctx"] = 16384
        options["num_predict"] = 4096
        options["temperature"] = 0.9
        options["top_k"] = 20
        
    data = {
        "model": model, 
        "prompt": prompt, 
        "stream": False,
        "options": options
    }
    if system_prompt:
        data["system"] = system_prompt
    if json_mode and "deepseek" not in model.lower():
        data["format"] = "json"
        
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=600) as response:
            result = json.loads(response.read().decode('utf-8'))
            resp_text = result.get('response', '').strip()
            # Extract and log thinking if any
            think_match = re.search(r'<think>(.*?)</think>', resp_text, flags=re.DOTALL)
            if think_match:
                think_content = think_match.group(1).strip()
                print(f"  [LLM Think]: {think_content}")
                log_to_file("think", think_content)
            resp_text = re.sub(r'<think>.*?</think>', '', resp_text, flags=re.DOTALL).strip()
            return resp_text
    except Exception as e:
        print(f"  [lean-export] Ollama error: {e}")
        return ""


_GEMINI_LAST_CALL_TIME = 0.0

def _get_gemini_cooldown_for_model(model_name, prompt_len):
    # Default fallback limits if model not strictly matched
    rpm, tpm = 15, 250000 
    
    model_lower = model_name.lower()
    if "flash-lite" in model_lower:
        rpm, tpm = 15, 250000
    elif "gemma" in model_lower:
        rpm, tpm = 15, 999999999  # Unlimited TPM
        
    delay_rpm = 60.0 / rpm
    tokens = prompt_len / 4.0
    delay_tpm = (tokens * 60.0) / tpm if tpm > 0 else 0
    
    # Add a small buffer (0.1s) to prevent exact boundary triggers
    return max(delay_rpm, delay_tpm) + 0.1

def query_gemini(prompt, system_prompt=None, client=None, model=None, json_mode=False):
    """Query Google Gemini API."""
    global _GEMINI_CLIENT, _GEMINI_MODEL_NAME, _GEMINI_LAST_CALL_TIME
    target_client = client or _GEMINI_CLIENT
    target_model = model or _GEMINI_MODEL_NAME
    
    if not target_client:
        print("  [lean-export] Gemini client not initialized!")
        return ""
    
    # Dynamic cooldown based on RPM/TPM
    full_len = len(prompt) + (len(system_prompt) if system_prompt else 0)
    cooldown = _get_gemini_cooldown_for_model(target_model, full_len)
    
    elapsed = time.time() - _GEMINI_LAST_CALL_TIME
    if elapsed < cooldown:
        wait_sec = cooldown - elapsed
        time.sleep(wait_sec)
        
    _GEMINI_LAST_CALL_TIME = time.time()
    try:
        contents = []
        if system_prompt:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=system_prompt)]))
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text="Understood.")]))
        if json_mode:
            prompt += "\nReturn strictly JSON format."
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))
        
        for attempt in range(5):
            try:
                # Gemma models often throw 500 Internal Error on temp=0.0 via Gemini API. Use temp=0.1.
                config_kwargs = {"temperature": 0.1, "max_output_tokens": 1024}
                if json_mode:
                    config_kwargs["response_mime_type"] = "application/json"
                    
                response = target_client.models.generate_content(
                    model=target_model,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs)
                )
                return response.text.strip()
            except Exception as e:
                err_str = str(e)
                if "429" in err_str:
                    wait_time = 30 + (attempt * 10)
                    print(f"  [gemini] Rate limit hit (429). Retry {attempt+1}/5, sleeping {wait_time}s...")
                    time.sleep(wait_time)
                elif "500" in err_str or "503" in err_str:
                    wait_time = 5 + (attempt * 3)
                    print(f"  [gemini] Server error ({'500' if '500' in err_str else '503'}). Retry {attempt+1}/5, sleeping {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise e
        return ""
    except Exception as e:
        print(f"  [lean-export] Gemini error: {e}")
        return ""

_OPENAI_LAST_CALL_TIME = 0.0

def query_openai(prompt, system_prompt=None, client=None, model=None, json_mode=False):
    """Query OpenAI API."""
    global _OPENAI_CLIENT, _OPENAI_MODEL_NAME, _OPENAI_LAST_CALL_TIME
    target_client = client or _OPENAI_CLIENT
    target_model = model or _OPENAI_MODEL_NAME
    
    if not target_client:
        print("  [lean-export] OpenAI client not initialized!")
        return ""
    
    # Проактивный cooldown (2с)
    elapsed = time.time() - _OPENAI_LAST_CALL_TIME
    if elapsed < 2.0:
        time.sleep(2.0 - elapsed)
    _OPENAI_LAST_CALL_TIME = time.time()
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if json_mode:
            prompt += "\nReturn strictly JSON format."
        messages.append({"role": "user", "content": prompt})
        
        # Configure OpenAI-compatible options dynamically
        kwargs = {
            "model": target_model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 1024,
        }
        
        if target_model and "goedel" in target_model.lower():
            kwargs["temperature"] = 0.9
            kwargs["max_tokens"] = 4096
            # Support top_k for local OpenAI-compatible llama.cpp / vLLM / Ollama API servers
            kwargs["extra_body"] = {"top_k": 20}
            
        for attempt in range(5):
            try:
                response = target_client.chat.completions.create(**kwargs)
                return response.choices[0].message.content.strip()
            except openai.RateLimitError as e:
                wait_time = 30 + (attempt * 10)
                print(f"  [openai] Rate limit hit. Sleeping {wait_time}s...")
                time.sleep(wait_time)
            except Exception as e:
                status_code = getattr(e, "status_code", None)
                if status_code in (401, 403, 404):
                    print(f"  [openai] Critical Error ({status_code}): {e}")
                    return ""
                print(f"  [openai] Error: {e}")
                time.sleep(5)
        return ""
    except Exception as e:
        print(f"  [lean-export] OpenAI error: {e}")
        return ""


_GROQ_LAST_CALL_TIME = 0.0



def query_groq(prompt, system_prompt=None, client=None, model=None, json_mode=False):
    """Query Groq API with TPM-aware cooldown and fail-fast for 401."""
    global _GROQ_CLIENT, _GROQ_MODEL_NAME, _GROQ_LAST_CALL_TIME
    target_client = client or _GROQ_CLIENT
    target_model = model or _GROQ_MODEL_NAME
    
    if not target_client:
        print("  [lean-export] Groq client not initialized!")
        return ""
    
    # Apply cooldown
    full_len = len(prompt) + (len(system_prompt) if system_prompt else 0)
    # We use the same cooldown logic based on the target model
    rpm, tpm = (30, 6000) # Default
    # (Simplified: in a real case we'd look up target_model in limits dict)
    # I'll keep the full logic from before.
    cooldown = _get_groq_cooldown_for_model(target_model, full_len)
    
    elapsed = time.time() - _GROQ_LAST_CALL_TIME
    if elapsed < cooldown:
        time.sleep(cooldown - elapsed)

    try:
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        if json_mode: prompt += "\nReturn strictly JSON format."
        messages.append({"role": "user", "content": prompt})
        
        for attempt in range(5):
            try:
                _GROQ_LAST_CALL_TIME = time.time()
                response = target_client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=1024,
                )
                return response.choices[0].message.content.strip()
            except openai.RateLimitError as e:
                wait_time = 30 + (attempt * 10)
                print(f"  [groq] Rate limit hit. Sleeping {wait_time}s...")
                time.sleep(wait_time)
            except Exception as e:
                status_code = getattr(e, "status_code", None)
                if status_code in (401, 403, 404):
                    print(f"  [groq] Critical Error ({status_code}): {e}")
                    return ""
                print(f"  [groq] Error: {e}")
                time.sleep(5)
        return ""
    except Exception as e:
        print(f"  [lean-export] Groq error: {e}")
        return ""

def _get_groq_cooldown_for_model(model_name, prompt_len):
    limits = {
        "allam-2-7b": (30, 6000), "orpheus-arabic-saudi": (10, 1200), "orpheus-v1-english": (10, 1200),
        "groq/compound": (30, 70000), "groq/compound-mini": (30, 70000),
        "llama-3.1-8b-instant": (30, 6000), "llama-3.3-70b-versatile": (30, 12000),
        "meta-llama/llama-4-scout-17b-16e-instruct": (30, 30000), "meta-llama/llama-prompt-guard-2-22m": (30, 15000),
        "meta-llama/llama-prompt-guard-2-86m": (30, 15000), "openai/gpt-oss-120b": (30, 8000),
        "openai/gpt-oss-20b": (30, 8000), "openai/gpt-oss-safeguard-20b": (30, 8000),
        "qwen/qwen3-32b": (60, 6000), "whisper-large-v3": (20, 2000), "whisper-large-v3-turbo": (20, 2000)
    }
    rpm, tpm = limits.get(model_name, (30, 6000))
    delay_rpm = 60.0 / rpm
    tokens = prompt_len / 4.0
    delay_tpm = (tokens * 60.0) / tpm if tpm > 0 else 0
    return max(delay_rpm, delay_tpm)

_HF_LAST_CALL_TIME = 0.0
_HF_COOLDOWN = 3.0  # Минимум 3 секунды между запросами к HF Spaces

def query_hf(prompt, system_prompt=None, client=None, model=None, json_mode=False):
    """Query Hugging Face Spaces via Gradio Client."""
    global _HF_CLIENT, _HF_MODEL_NAME, _HF_LAST_CALL_TIME
    target_client = client or _HF_CLIENT
    target_model = model or _HF_MODEL_NAME
    
    if not target_client:
        print("  [lean-export] HF client not initialized!")
        return ""
    
    # Проактивный cooldown — защита от бана IP
    elapsed = time.time() - _HF_LAST_CALL_TIME
    if elapsed < _HF_COOLDOWN:
        wait = _HF_COOLDOWN - elapsed
        print(f"  [hf] Cooldown: waiting {wait:.1f}s...")
        time.sleep(wait)
        
    if json_mode:
        prompt += "\nReturn strictly JSON format."
        
    _HF_LAST_CALL_TIME = time.time()
    try:
        # Retry loop for potential 504 Gateway Timeouts or queue errors
        for attempt in range(5):
            try:
                # Mappings for specific supported spaces
                if "Qwen2.5-72B-Instruct" in target_model:
                    # Space: Qwen/Qwen2.5-72B-Instruct
                    # Signature: (query, history, system) -> output
                    res = target_client.predict(
                        query=prompt,
                        history=[],
                        system=system_prompt if system_prompt else "You are a helpful assistant.",
                        api_name="/model_chat"
                    )
                    return str(res[1][0][-1]).strip() if isinstance(res, (list, tuple)) and len(res) > 1 else str(res).strip()
                elif "Qwen2.5-Coder-32B-Instruct" in target_model:
                    # Space: Qwen/Qwen2.5-Coder-32B-Instruct
                    res = target_client.predict(
                        query=prompt,
                        history=[],
                        system=system_prompt if system_prompt else "You are a helpful coding assistant.",
                        api_name="/model_chat"
                    )
                    return str(res[1][0][-1]).strip() if isinstance(res, (list, tuple)) and len(res) > 1 else str(res).strip()
                elif "c4ai-command-r-plus" in target_model:
                    # Space: CohereForAI/c4ai-command-r-plus-08-2024
                    res = target_client.predict(
                        message=prompt,
                        chat_history=[],
                        system_message=system_prompt if system_prompt else "You are a helpful assistant.",
                        max_tokens=1024,
                        temperature=0.0,
                        top_p=0.9,
                        api_name="/chat"
                    )
                    return str(res).strip()
                elif "Mixtral-8x22B-Instruct-v0.1" in target_model:
                    # Space: mistralai/Mixtral-8x22B-Instruct-v0.1
                    res = target_client.predict(
                        message=prompt,
                        system_message=system_prompt if system_prompt else "You are a helpful assistant.",
                        max_new_tokens=1024,
                        temperature=0.0,
                        top_p=0.9,
                        top_k=50,
                        repetition_penalty=1.0,
                        api_name="/chat"
                    )
                    return str(res).strip()
                elif "gemma-4-31b-it" in target_model or "gemma-4" in target_model.lower():
                    # Space: huggingface-projects/gemma-4-31b-it
                    # API: /generate — message is a dict {text, files}
                    res = target_client.predict(
                        message={"text": prompt, "files": []},
                        thinking=False,
                        max_new_tokens=1024,
                        max_soft_tokens="280",
                        system_prompt=system_prompt if system_prompt else "You are a helpful assistant.",
                        api_name="/generate"
                    )
                    # Response is JSON: could be str or dict
                    if isinstance(res, dict):
                        return str(res.get("text", res)).strip()
                    return str(res).strip()
                else:
                    # Generic heuristic fallback
                    res = target_client.predict(
                        prompt,
                        api_name="/chat"
                    )
                    return str(res).strip()
            except Exception as e:
                err_msg = str(e).lower()
                if "timeout" in err_msg or "504" in err_msg or "rate limit" in err_msg or "queue" in err_msg:
                    wait_time = 30 + (attempt * 10)
                    print(f"  [hf] Retryable error ({e}). Sleeping {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"  [hf] Critical Error: {e}")
                    return ""
        return ""
    except Exception as e:
        print(f"  [lean-export] HF error: {e}")
        return ""


def query_llm(prompt, model=None, system_prompt=None, json_mode=False, provider=None):
    """Routes to the active LLM provider (ollama, gemini, openai, groq, or hf).
    If provider == 'preview', routes to the configured preview provider (setup_preview_provider).
    """
    # Use explicit provider, otherwise main provider
    use_preview = False
    if provider == 'preview':
        # route to preview provider settings
        active_provider = _PREVIEW_PROVIDER
        use_preview = True
    else:
        active_provider = provider or _LLM_PROVIDER
    
    if active_provider == "gemini":
        if use_preview:
            client = _PREVIEW_GEMINI_CLIENT or _GEMINI_CLIENT
            model_name = _PREVIEW_GEMINI_MODEL or _GEMINI_MODEL_NAME or model
        else:
            client = _LEAN_GEMINI_CLIENT or _GEMINI_CLIENT
            model_name = _LEAN_GEMINI_MODEL or _GEMINI_MODEL_NAME or model
        result = query_gemini(prompt, system_prompt=system_prompt, client=client, model=model_name, json_mode=json_mode)
    elif active_provider == "openai":
        if use_preview:
            client = _PREVIEW_OPENAI_CLIENT or _OPENAI_CLIENT
            model_name = _PREVIEW_OPENAI_MODEL or _OPENAI_MODEL_NAME or model
        else:
            client = _LEAN_OPENAI_CLIENT or _OPENAI_CLIENT
            model_name = _LEAN_OPENAI_MODEL or _OPENAI_MODEL_NAME or model
        result = query_openai(prompt, system_prompt=system_prompt, client=client, model=model_name, json_mode=json_mode)
    elif active_provider == "groq":
        if use_preview:
            client = _PREVIEW_GROQ_CLIENT or _GROQ_CLIENT
            model_name = _PREVIEW_GROQ_MODEL or _GROQ_MODEL_NAME or model
        else:
            client = _LEAN_GROQ_CLIENT or _GROQ_CLIENT
            model_name = _LEAN_GROQ_MODEL or _GROQ_MODEL_NAME or model
        result = query_groq(prompt, system_prompt=system_prompt, client=client, model=model_name, json_mode=json_mode)
    elif active_provider == "hf":
        if use_preview:
            client = _PREVIEW_HF_CLIENT or _HF_CLIENT
            model_name = _PREVIEW_HF_MODEL or _HF_MODEL_NAME or model
        else:
            client = _LEAN_HF_CLIENT or _HF_CLIENT
            model_name = _LEAN_HF_MODEL or _HF_MODEL_NAME or model
        result = query_hf(prompt, system_prompt=system_prompt, client=client, model=model_name, json_mode=json_mode)
    elif active_provider == "llama_cpp":
        # Local llama.cpp via llama-cpp-python
        if use_preview:
            client = _PREVIEW_LLAMA_CPP_CLIENT or _LLAMA_CPP_CLIENT
            model_name = _PREVIEW_LLAMA_CPP_MODEL or _LLAMA_CPP_MODEL or model
        else:
            client = _LEAN_LLAMA_CPP_CLIENT or _LLAMA_CPP_CLIENT
            model_name = _LEAN_LLAMA_CPP_MODEL or _LLAMA_CPP_MODEL or model
        global _LLAMA_CPP_WARNED
        if not client:
            if not _LLAMA_CPP_WARNED:
                print("  [lean-export] llama.cpp client not initialized! Skipping local llama.cpp calls.")
                _LLAMA_CPP_WARNED = True
            result = ""
        else:
            try:
                # Limit max_tokens to avoid exceeding model context window (small models like reranker)
                max_tokens_req = 32 if use_preview else 256
                resp = client(prompt=prompt, max_tokens=max_tokens_req, temperature=0.0)
                if isinstance(resp, dict):
                    choices = resp.get('choices', [])
                    if choices:
                        result = str(choices[0].get('text', '')).strip()
                    else:
                        result = str(resp.get('text', '')).strip()
                else:
                    result = str(resp).strip()
            except Exception as e:
                if not _LLAMA_CPP_WARNED:
                    print(f"  [lean-export] llama.cpp error: {e}")
                    _LLAMA_CPP_WARNED = True
                result = ""
    else:
        if use_preview:
            model_name = _PREVIEW_OLLAMA_MODEL or _OLLAMA_MODEL or model
        else:
            model_name = _LEAN_OLLAMA_MODEL or _OLLAMA_MODEL or model
        result = query_ollama(prompt, model=model_name, system_prompt=system_prompt, json_mode=json_mode)

    # Strip `<think>...</think>` tags globally to prevent reasoning blocks from breaking JSON or text parsers
    if result and "<think>" in result:
        think_match = re.search(r'<think>(.*?)</think>', result, flags=re.DOTALL)
        if think_match:
            think_content = think_match.group(1).strip()
            log_to_file("think", think_content)
        result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL).strip()
    return result




# ── Graph Discovery ──────────────────────────────────────────────────────────

def get_graph_from_files():
    """Scans content/ for entities and their dependencies."""
    nodes = {}
    edges = []

    for filepath in CONTENT_DIR.rglob("*.tex"):
        if filepath.name in ("master.tex", "TEMPLATE.tex", "mathesis.sty"):
            continue
        match = re.search(r'\[([^\]]+)\]\.tex$', filepath.name)
        if not match:
            continue

        entity_id = match.group(1)
        try:
            content = filepath.read_text(encoding='utf-8')
        except Exception:
            continue

        # Detect type from comment or environment
        type_match = re.search(r'% entity-type:\s*(\w+)', content)
        entity_type = type_match.group(1) if type_match else "object"

        nodes[entity_id] = {"type": entity_type, "path": filepath}

        # Extract dependencies
        deps = set(re.findall(r'\\entityref\{([^}]+)\}', content))
        for dep in deps:
            if dep != entity_id:
                edges.append((entity_id, dep))

    return nodes, edges


def topological_sort(nodes, edges):
    graph = defaultdict(list)
    in_degree = {n: 0 for n in nodes}

    for u, v in edges:
        if u in nodes and v in nodes:
            graph[v].append(u)
            in_degree[u] += 1

    queue = deque([n for n in nodes if in_degree[n] == 0])
    sorted_nodes = []

    while queue:
        curr = queue.popleft()
        sorted_nodes.append(curr)
        for neighbor in graph[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Catch cycles
    for n in nodes:
        if n not in sorted_nodes:
            sorted_nodes.append(n)

    return sorted_nodes


# ── LLM Translation ─────────────────────────────────────────────────────────

def is_semantic_error(lean_code: str, errors: list, entity_type: str) -> bool:
    """
    Determines if Lean compiler errors or generated code indicate a structural/semantic flaw
    that requires fixing the original LaTeX formulation (e.g. missing assumptions).
    """
    # Check compiler errors for structural hints
    for err in errors:
        msg = err.get("message", "").lower()
        if "type mismatch" in msg:
            return True
        if "failed to synthesize instance" in msg:
            return True
        if "don't know how to synthesize placeholder" in msg:
            return True
            
    return False


def translate_to_lean_via_llm(entity_id, entity_type, tex_content, model="goedel:latest", mathlib_hints="", error_feedback=None, previous_code=None, attempt=None):
    """
    Translates LaTeX to Lean 4 using LLM, supporting error feedback for self-correction.
    """
    global _LEAN_PROVIDER, _LEAN_OLLAMA_MODEL, _LEAN_GEMINI_MODEL, _LEAN_OPENAI_MODEL, _LEAN_GROQ_MODEL, _LEAN_HF_MODEL, _LEAN_LLAMA_CPP_MODEL, _LLM_PROVIDER
    
    tex_clean = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', tex_content, flags=re.DOTALL)
    tex_clean = re.sub(r'^%.*$', '', tex_clean, flags=re.MULTILINE).strip()
    if not tex_clean:
        return ""

    lean_name = entity_id.replace('-', '_')

    # Resolve target provider and model for Lean generation
    target_provider = _LEAN_PROVIDER or _LLM_PROVIDER
    target_model = model
    
    if _LEAN_PROVIDER:
        if _LEAN_PROVIDER == "ollama" and _LEAN_OLLAMA_MODEL:
            target_model = _LEAN_OLLAMA_MODEL
        elif _LEAN_PROVIDER == "gemini" and _LEAN_GEMINI_MODEL:
            target_model = _LEAN_GEMINI_MODEL
        elif _LEAN_PROVIDER == "openai" and _LEAN_OPENAI_MODEL:
            target_model = _LEAN_OPENAI_MODEL
        elif _LEAN_PROVIDER == "groq" and _LEAN_GROQ_MODEL:
            target_model = _LEAN_GROQ_MODEL
        elif _LEAN_PROVIDER == "hf" and _LEAN_HF_MODEL:
            target_model = _LEAN_HF_MODEL
        elif _LEAN_PROVIDER == "llama_cpp" and _LEAN_LLAMA_CPP_MODEL:
            target_model = _LEAN_LLAMA_CPP_MODEL

    if not target_model:
        target_model = "goedel:latest"

    # Decryption guide of custom LaTeX macros used in the project
    latex_decryption_guide = """=== LaTeX Project Macro Translation Guide ===
Our LaTeX formulas use custom macro abbreviations that must be translated to standard Lean 4 syntax:
* \\mForall{x \\in X} or \\mForall{x \\colon X} -> universal quantifier (∀ x ∈ X, ...) or (∀ x : X, ...)
* \\mExists{x \\in X} or \\mExists{x \\colon X} -> existential quantifier (∃ x ∈ X, ...) or (∃ x : X, ...)
* \\mIff -> logical equivalence / iff (↔)
* \\mImplies -> logical implication (→)
* \\entityref{entity-id}{text} -> represents a reference to a core mathematical object/type. Translate to appropriate Lean types:
  - \\entityref{obj-real-numbers}{\\mathbb{R}} -> Real numbers (ℝ)
  - \\entityref{obj-natural-numbers}{\\mathbb{N}} -> Natural numbers (ℕ)
  - \\entityref{obj-rational-numbers}{\\mathbb{Q}} -> Rational numbers (Rat)
  - \\entityref{op-abs-abstract}{\\mathrm{abs}}(x) -> Absolute value function (|x| or Real.abs x)
* \\left( and \\right) -> standard parentheses ( and )"""

    # Declaration rules based on Entity Type
    declaration_rules = f"""=== Lean 4 Declaration Mapping Rules ===
The target entity has type: '{entity_type}'. You MUST follow these strict mapping rules based on this type:
1. If the type is 'operation', 'definition', 'object' or 'property':
   - Declare EXACTLY ONE `def`. 
   - EXAMPLE OF EXPECTED OUTPUT:
     ```lean4
     def {lean_name} (f : ℝ → ℝ) (x L : ℝ) : Prop := ...
     ```
   - CRITICAL: DO NOT create any additional `theorem` or `lemma` blocks! Stop generation right after the `def`.
   - CRITICAL: DO NOT attempt to prove equivalence to Mathlib concepts (like Filter.Tendsto).
   - If the LaTeX contains \\mIff or \\mDefinedAs, extract the right-hand side and use it as the body of your `def`.
   - DO NOT use sorry under any circumstances!
   - ANTI-SHADOWING RULE: Never use the same variable name for a collection and its element (e.g., instead of `∃ B ∈ B`, you MUST use `∃ B' ∈ B` or `∃ U ∈ B`).
2. If the type is 'theorem':
   - Declare it as a `theorem`. Format: `theorem {lean_name} ... : ... := by sorry`
   - `sorry` is ALLOWED for theorem proofs.
3. If the type is 'axiom' or 'foundation':
   - Declare it as an `axiom`. Format: `axiom {lean_name} ... : ...`"""

    # Detect if we are using the Goedel-Formalizer model
    is_goedel = "goedel" in target_model.lower()

    if is_goedel:
        problem_name = lean_name
        informal_statement_content = f"We define a mathematical {entity_type}.\n"
        informal_statement_content += f"Formal definition/theorem in LaTeX:\n${tex_clean}$\n"
        if mathlib_hints:
            informal_statement_content += f"\nRelevant Mathlib signatures:\n{mathlib_hints}\n"
            
        informal_statement_content += f"\n{declaration_rules}\n\n{latex_decryption_guide}\n"
        system_prompt = None

        # Смена фрейма и Prefix Forcing для определений
        if entity_type in ["object", "operation", "definition", "property"]:
            system_intro = f"Please formalize the following mathematical definition in Lean 4 as a pure `def`. Use the following definition name: {problem_name}"
            prefix_hint = f"\n\nCRITICAL: Output ONLY the Lean code. You MUST start your code exactly like this:\n```lean4\ndef {lean_name}"
        else:
            system_intro = f"Please autoformalize the following natural language problem statement in Lean 4. Use the following theorem name: {problem_name}"
            prefix_hint = ""

        if error_feedback and previous_code:
            user_prompt = f"""{system_intro}
The natural language statement is: 
{informal_statement_content}

CRITICAL: The previous Lean 4 attempt produced compiler errors. 
Previous Lean 4 code:
{previous_code}

Compiler Errors:
{error_feedback}

Please correct the Lean 4 code so it compiles successfully.
Think before you provide the lean statement.{prefix_hint}"""
        else:
            user_prompt = f"""{system_intro}
The natural language statement is: 
{informal_statement_content}
Think before you provide the lean statement.{prefix_hint}"""
    else:
        # Standard system prompt for general instruction models
        system_prompt = f"""You are an expert mathematician and a Lean 4 formalization specialist.
Your task is to translate mathematical statements into valid Lean 4 declarations.

Textbooks use informal Set Theory (ZFC) and often abuse notation. Your target environment (Lean 4) uses strict Type Theory (Calculus of Inductive Constructions). You must bridge this gap by performing a rigorous semantic translation before generating the final code.

CRITICAL HEURISTICS & ANTI-PATTERNS TO AVOID:
1. Types vs. Sets (The \colon vs \in rule): 
   Never confuse belonging to a fundamental type with belonging to a subset. 
   - BAD: "x \in \mathbb{R}" when declaring a variable. 
   - GOOD: "x \colon \mathbb{R}" (in LaTeX) or "(x : ℝ)" (in Lean). Use "\in" ONLY for subsets, e.g., "x \in [a, b]".

2. Analytical vs. Computational Structures (The List rule):
   Never use computational data structures like `List` or `Array` to represent continuous mathematical concepts (partitions, sequences, covers).
   - BAD: Representing a partition as `P : List ℝ`.
   - GOOD: Representing a partition as a function `(n : ℕ) (t : ℕ → ℝ)` bounded by `Finset.range n`.

3. Unpacking Informal Notation (The Ellipsis rule):
   Textbooks use informal ellipses like "{{t_0, ..., t_n}}". You must explicitly unpack these into rigorous functions and index bounds. Identify implicit dependencies (e.g., if a sequence is finite, you must introduce its length `n : ℕ` as a separate variable).

4. Tautology & Complexity Check:
   If you find yourself writing repetitive logical tautologies (e.g., `x ≠ y → x ≠ y`) or overly complex index bounds, your underlying type choice is wrong. Stop and re-evaluate your data structures.

5. Strict Semantic Identifiers (The Self-Describing ID Rule):
   When generating \entityref{id}{text} or defining a new entity-id, the `id` MUST be globally unambiguous, self-documenting, and resistant to namespace collisions. 
   
   NEVER use bare, generic nouns or adjectives. You MUST include the domain or the parent mathematical object in the ID.
   
   Format: {type}-{domain_or_parent}-{concept}
   
   - BAD: `op-mesh` (Mesh of what? A graph? A 3D model? A partition?)
   - GOOD: `op-partition-mesh` (Clearly states this is the mesh of a partition)
   
   - BAD: `prop-bounded` (Is a function bounded? A set? A sequence?)
   - GOOD: `prop-function-bounded` or `prop-set-bounded`
   
   - BAD: `op-addition` 
   - GOOD: `op-real-addition` or `op-matrix-addition` (Unless using the Late Binding abstract pattern like `op-add-abstract`)

   If a concept belongs to a specific mathematical domain, prefix it explicitly to help the Lean 4 translator map it to the correct Mathlib namespace.

OUTPUT FORMAT:
Before writing the final Lean 4 code, you MUST output a `<semantic_mapping>` block where you explicitly map the informal concepts to their strict Type Theory equivalents:

<semantic_mapping>
1. Variables & Types: [List all variables and state whether they are Types (:) or Sets (∈)]
2. Data Structures: [Explain how you will represent complex objects like partitions or sequences]
3. Implicit Bounds: [List any hidden variables, like `n : ℕ`, needed to make the definition strict]
</semantic_mapping>

[Your final Lean 4 code block follows here enclosed in ```lean ... ```]

{declaration_rules}

{latex_decryption_guide}

RULES:
1. Output the `<semantic_mapping>` block first, then the valid Lean 4 code block. No additional markdown formatting, no explanations outside these blocks, no `import` statements.
2. Use Mathlib types: ℝ, ℕ, ℤ, Set, Prop, Type.
3. ALL variables must be bound explicitly (∀ or ∃).
4. Do NOT use LaTeX commands (\\forall, \\in, \\mathbb, etc.)."""

        if error_feedback and previous_code:
            user_prompt = f"""The following Lean 4 code generated for entity '{lean_name}' produced compiler errors.
Code:
{previous_code}

Compiler Errors:
{error_feedback}

Fix the Lean 4 code. Output ONLY the fixed code."""
        else:
            user_prompt = f"""Entity Type: {entity_type}
Name: {lean_name}

LaTeX Source:
{tex_clean}

Mathlib Hints:
{mathlib_hints}

Lean 4 Code:"""

        if error_feedback and previous_code:
            user_prompt = f"""The following Lean 4 code generated for entity '{lean_name}' produced compiler errors.
Code:
{previous_code}

Compiler Errors:
{error_feedback}

Fix the Lean 4 code. Output ONLY the fixed code."""
        else:
            user_prompt = f"""Entity Type: {entity_type}
Name: {lean_name}

LaTeX Source:
{tex_clean}

Mathlib Hints:
{mathlib_hints}

Lean 4 Code:"""

    response = query_llm(user_prompt, model=target_model, system_prompt=system_prompt, provider=target_provider)
    
    # Log synthesis prompt and response
    synth_log = f"=== SYSTEM PROMPT ===\n{system_prompt}\n\n=== PROMPT ===\n{user_prompt}\n\n=== RESPONSE ===\n{response}\n"
    log_to_file("synthesis/lean", synth_log, entity_id=entity_id, attempt=attempt)
    
    # Extract Lean code blocks robustly
    prompt_ends_in_code_block = is_goedel and entity_type in ["object", "operation", "definition", "property"]
    
    parts = re.split(r'```(?:lean|lean4)?\s*', response, flags=re.IGNORECASE)
    blocks = []
    if prompt_ends_in_code_block:
        # Segment 0 is the immediate completion of the prefix
        if parts[0].strip():
            blocks.append(parts[0].strip())
        # Other segments are in between backticks
        for i in range(2, len(parts), 2):
            blocks.append(parts[i].strip())
    else:
        for i in range(1, len(parts), 2):
            blocks.append(parts[i].strip())
            
    if not blocks:
        clean = re.sub(r'^```(?:lean|lean4)?\s*', '', response, flags=re.MULTILINE | re.IGNORECASE)
        clean = re.sub(r'^```\s*$', '', clean, flags=re.MULTILINE)
        if clean.strip():
            blocks.append(clean.strip())
            
    # Select the best block containing actual Lean declarations
    if blocks:
        best_block = blocks[-1]
        for b in reversed(blocks):
            if "def " in b or "theorem " in b or "axiom " in b:
                best_block = b
                break
                
        if prompt_ends_in_code_block and best_block == blocks[0]:
            response = f"def {lean_name} {best_block}"
        else:
            response = best_block
    else:
        response = response.strip()
        
    # Clean up LLM completion prefix junk (like '4', 'lean', 'lean4') on the first line
    lines = response.splitlines()
    if lines and lines[0].strip() in ("4", "lean", "lean4"):
        lines = lines[1:]
    response = "\n".join(lines).strip()
    
    # Auto-heal cheat patterns where reasoning models define helper defs and theorem equivalents
    if entity_type in ["object", "property", "operation"]:
        helper_matches = re.findall(r'\bdef\s+([A-Za-z0-9_]+)\b', response)
        helpers = [h for h in helper_matches if h != lean_name]
        
        if helpers and lean_name not in helper_matches:
            has_theorem = re.search(rf'\b(theorem|lemma)\s+{lean_name}\b', response)
            if has_theorem:
                helper_to_rename = helpers[0]
                print(f"  [Auto-Heal] Renaming helper '{helper_to_rename}' to target '{lean_name}' and removing theorem.")
                response = re.sub(rf'\bdef\s+{helper_to_rename}\b', f'def {lean_name}', response)
                response = re.sub(rf'\b(theorem|lemma)\s+{lean_name}\b.*', '', response, flags=re.DOTALL).strip()
                
        elif not re.search(r'\bdef\b', response) and re.search(rf'\b(theorem|lemma)\s+{lean_name}\b', response):
            print(f"  [Auto-Heal] Changing theorem '{lean_name}' to def.")
            response = re.sub(rf'\b(theorem|lemma)\s+{lean_name}\b', f'def {lean_name}', response)
    
    # Log Lean code
    if response:
        log_to_file("lean_code", response, entity_id=entity_id, attempt=attempt)
        
    print(f"  [lean-export] Сгенерированный код Lean:\n{response}\n")

    # Forbid 'noncomputable' in generated Lean code per policy
    if 'noncomputable' in response.lower():
        print(f"  [lean-export] REJECTING: 'noncomputable' used in generated code (forbidden).")
        return ""

    if '\\' in response and ('\\mathcal' in response or '\\in' in response or '\\mForall' in response):
        print(f"  [lean-export] LLM output still contains LaTeX. Rejecting.")
        return ""

    return response.strip()


# ── Regex Fallback Translation ───────────────────────────────────────────────

def translate_to_lean_regex(entity_id, entity_type, tex_content):
    """Legacy regex-based translation. Used as fallback when LLM fails."""
    formulas = re.findall(r'\\\[(.*?)\\\]', tex_content, re.DOTALL)
    if not formulas:
        return ""

    math = " ".join(formulas)
    lean_name = entity_id.replace('-', '_')

    replacements = [
        # Quantifiers (Parameterized)
        (r'\\mForall\{([^}]+)\}', r'∀ \1, '),
        (r'\\mExists\{([^}]+)\}', r'∃ \1, '),
        
        # Mappings
        (r'\\mMap\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}', r'\1 : \2 → \3'),

        # Quantifiers (Standalone)
        (r'\\mForall', '∀'), (r'\\forall', '∀'),
        (r'\\mExists', '∃'), (r'\\exists', '∃'),

        # Logic Connectives
        (r'\\mImplies', '→'), (r'\\Rightarrow', '→'), (r'\\implies', '→'),
        (r'\\mIff', '↔'), (r'\\Leftrightarrow', '↔'), (r'\\iff', '↔'),
        (r'\\mDefIff', ':='), (r'\\mDefinedAs', ':='),
        (r'\\mAnd', '∧'), (r'\\land', '∧'),
        (r'\\mOr', '∨'), (r'\\lor', '∨'),
        (r'\\mNot', '¬'), (r'\\lnot', '¬'),
        (r'\\mTurnstile', '⊢'), (r'\\vdash', '⊢'),

        # Sets
        (r'\\mIn', '∈'), (r'\\in', '∈'),
        (r'\\mSubseteq', '⊆'), (r'\\subseteq', '⊆'),
        (r'\\mSubset', '⊆'), (r'\\subset', '⊆'),
        (r'\\mEmpty', '∅'), (r'\\varnothing', '∅'), (r'\\emptyset', '∅'),

        # Number Sets
        (r'\\mReal', 'ℝ'), (r'\\mathbb\{R\}', 'ℝ'),
        (r'\\mNat', 'ℕ'), (r'\\mathbb\{N\}', 'ℕ'),
        (r'\\mInt', 'ℤ'), (r'\\mathbb\{Z\}', 'ℤ'),
        (r'\\mComplex', 'ℂ'), (r'\\mathbb\{C\}', 'ℂ'),

        # Formatting / Structural
        (r'\\entityref\{[^}]+\}\{(.*?)\}', r'\1'),
        (r'\\quad', ' '), (r'\\;', ' '),
        (r'\\text\{([^}]+)\}', r'\1'),
        (r'\\left', ''), (r'\\right', ''),
        (r'\\colon', ':'),
        (r'\\mTo', '→'), (r'\\to', '→'),

        # Relational / Variables
        (r'\\neq', '≠'),
        (r'\\leq', '≤'), (r'\\le', '≤'),
        (r'\\geq', '≥'), (r'\\ge', '≥'),
        (r'\\varepsilon', 'ε'), (r'\\delta', 'δ'),
        (r'\\infty', '∞'),
        (r'\\mathcal\{([^}]+)\}', r'\1'),
        (r'\n', ' '),
    ]

    lean_math = math
    for pattern, repl in replacements:
        lean_math = re.sub(pattern, repl, lean_math)
    lean_math = re.sub(r'\s+', ' ', lean_math).strip()

    # Format by type
    if entity_type == "axiom":
        return f"axiom {lean_name} : {lean_math}"
    elif entity_type == "object":
        return f"axiom {lean_name} : Type"
    elif entity_type == "property":
        return f"def {lean_name} : Prop := sorry"
    elif entity_type in ("theorem", "operation"):
        return f"axiom {lean_name} : {lean_math}"

    return f"-- Unrecognized type: {lean_name}"


# ── Generation with Repair Loop ──────────────────────────────────────────────

def attempt_generation_with_repair(eid, entity_type, tex_content, model="goedel:latest", max_attempts=7):
    """
    Loop: Generate -> Validate -> Analyze errors -> Regenerate.
    Returns: (lean_code, is_valid)
    """
    lean_code = ""
    error_feedback = None

    for attempt in range(1, max_attempts + 1):
        lean_code = translate_to_lean_via_llm(
            eid, entity_type, tex_content, 
            model=model,
            error_feedback=error_feedback, 
            previous_code=lean_code,
            attempt=attempt
        )
        
        if not lean_code:
            return None, False

        validation_result = validate_entity(eid, lean_code)
        
        if validation_result["status"] == "success":
            print(f"  [✓] {eid} успешно валидирован (Попытка {attempt})")
            return lean_code, True
            
        elif validation_result["status"] == "failed":
            errors = validation_result.get("errors", [])
            error_feedback = "\n".join([f"Line {e['line']}: {e['message']}" for e in errors])
            print(f"  [!] {eid} ошибка (Попытка {attempt}/{max_attempts}). Отправляем фидбек модели...")
            log_to_file("lean_errors", error_feedback, entity_id=eid, attempt=attempt)
            
    return lean_code, False


# ── Main Export Pipeline ─────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export Mathesis graph to Lean 4")
    parser.add_argument("--model", type=str, default=None, help="LLM model name")
    parser.add_argument("--api-key", type=str, default=None, help="API Key for cloud providers")
    parser.add_argument("--force", action="store_true", help="Re-translate all entities")
    parser.add_argument("--provider", type=str, default="ollama", choices=["ollama", "gemini", "openai", "groq"],
                        help="Main LLM provider")
    parser.add_argument("--lean-provider", type=str, default=None, choices=["ollama", "gemini", "openai", "groq"],
                        help="Optional separate provider for Lean generation")
    parser.add_argument("--lean-api-key", type=str, default=None, help="API Key for Lean provider")
    parser.add_argument("--lean-model", type=str, default=None, help="Model for Lean provider")
    args = parser.parse_args()

    # Default models per provider
    if not args.model:
        if args.provider == "gemini": args.model = "gemini-2.5-flash"
        elif args.provider == "openai": args.model = "gpt-4o-mini"
        elif args.provider == "groq": args.model = "llama-3.3-70b-versatile"
        else: args.model = "qwen3:8b"
    
    if args.lean_provider and not args.lean_model:
        if args.lean_provider == "gemini": args.lean_model = "gemini-2.5-flash"
        elif args.lean_provider == "openai": args.lean_model = "gpt-4o-mini"
        elif args.lean_provider == "groq": args.lean_model = "llama-3.3-70b-versatile"
        else: args.lean_model = "qwen3:8b"

    # Initialize LLM providers
    setup_provider(args.provider, api_key=args.api_key, model=args.model)
    if args.lean_provider:
        setup_lean_provider(args.lean_provider, api_key=args.lean_api_key, model=args.lean_model)



    print("=== Exporting Mathesis graph to Lean 4 ===")

    nodes, edges = get_graph_from_files()
    sorted_ids = topological_sort(nodes, edges)

    if not sorted_ids:
        print("No entities found.")
        return

    VALIDATED_DIR.mkdir(parents=True, exist_ok=True)
    LEAN_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize file for successful entities
    with open(SUCCESS_FILE, 'w', encoding='utf-8') as f:
        f.write("import Mathlib\n\n-- Valid entities generated by Goedel-Formalizer\n\n")

    lean_fragments = []
    stats = {"llm_ok": 0, "regex_ok": 0, "failed": 0, "cached": 0}

    for eid in sorted_ids:
        node = nodes[eid]
        validated_file = VALIDATED_DIR / f"{eid}.lean"

        # Skip if already validated (unless --force)
        if validated_file.exists() and not args.force:
            lean_code = validated_file.read_text(encoding='utf-8')
            lean_fragments.append((eid, lean_code))
            stats["cached"] += 1
            
            # Since it's cached, optionally we can add it to SUCCESS_FILE if we assume it's valid,
            # but we won't double-append to prevent duplicates unless we do a fresh run.
            continue

        try:
            content = node["path"].read_text(encoding='utf-8')
        except Exception as e:
            print(f"  [SKIP] {eid}: {e}")
            stats["failed"] += 1
            continue

        # Strip proof blocks for translation
        content_no_proofs = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', content, flags=re.DOTALL)

        # Use new self-correction loop
        lean_code, is_valid = attempt_generation_with_repair(eid, node["type"], content_no_proofs, model=args.model)

        if lean_code and is_valid:
            print(f"  [LLM] {eid} → OK ({len(lean_code)} chars)")
            stats["llm_ok"] += 1
            validated_file.write_text(lean_code, encoding='utf-8')
            lean_fragments.append((eid, lean_code))
            
            with open(SUCCESS_FILE, 'a', encoding='utf-8') as sf:
                sf.write(f"-- Entity: {eid} | Type: {node['type']}\n")
                sf.write(f"{lean_code}\n\n")
        else:
            # Fallback (Regex) with additional validation
            lean_code_regex = translate_to_lean_regex(eid, node["type"], content_no_proofs)
            if lean_code_regex:
                regex_val = validate_entity(eid, lean_code_regex)
                if regex_val["status"] == "success":
                    print(f"  [REGEX] {eid} → fallback валиден")
                    stats["regex_ok"] += 1
                    validated_file.write_text(lean_code_regex, encoding='utf-8')
                    lean_fragments.append((eid, lean_code_regex))
                    
                    with open(SUCCESS_FILE, 'a', encoding='utf-8') as sf:
                        sf.write(f"-- Entity: {eid} (Regex Fallback)\n{lean_code_regex}\n\n")
                else:
                    print(f"  [REGEX] {eid} → fallback также не прошел валидацию")
                    stats["failed"] += 1
            else:
                print(f"  [SKIP] {eid} → no translatable content")
                stats["failed"] += 1

    # Assemble MathesisGraph.lean
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write("import Mathlib\n\n")
        f.write("-- Auto-generated by pipeline/export_to_lean.py\n")
        f.write(f"-- Entities: {len(lean_fragments)}\n\n")

        for eid, code in lean_fragments:
            f.write(f"-- {eid}\n")
            f.write(f"{code}\n\n")

    print(f"\n=== Export complete ===")
    print(f"  LLM translations (OK): {stats['llm_ok']}")
    print(f"  Regex fallbacks (OK):  {stats['regex_ok']}")
    print(f"  Cached:                {stats['cached']}")
    print(f"  Failed/skipped:        {stats['failed']}")
    print(f"  Successful entities:   {SUCCESS_FILE}")
    print(f"  Output Graph:          {OUT_FILE}")


if __name__ == "__main__":
    main()
