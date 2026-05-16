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

from lean_validator import validate_entity

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"
LEAN_DIR = PROJECT_ROOT / "lean_validator"
VALIDATED_DIR = LEAN_DIR / "Validated"
OUT_FILE = LEAN_DIR / "MathesisGraph.lean"
SUCCESS_FILE = LEAN_DIR / "SuccessfulEntities.lean"

# Active LLM provider config (set by main() or setup_provider())
_LLM_PROVIDER = "ollama"  
_GEMINI_CLIENT = None
_GEMINI_MODEL_NAME = None
_OPENAI_CLIENT = None
_OPENAI_MODEL_NAME = None
_GROQ_CLIENT = None
_GROQ_MODEL_NAME = None
_HF_CLIENT = None
_HF_MODEL_NAME = None

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
    global _LLM_PROVIDER, _GEMINI_CLIENT, _GEMINI_MODEL_NAME, _OPENAI_CLIENT, _OPENAI_MODEL_NAME, _GROQ_CLIENT, _GROQ_MODEL_NAME, _HF_CLIENT, _HF_MODEL_NAME
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
        _OPENAI_CLIENT = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()
        if model: _OPENAI_MODEL_NAME = model
    elif _LLM_PROVIDER == "groq":
        if not OPENAI_AVAILABLE:
            print("ERROR: openai/groq compatible SDK not installed.")
            return
        _GROQ_CLIENT = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1") if api_key else openai.OpenAI(base_url="https://api.groq.com/openai/v1")
        if model: _GROQ_MODEL_NAME = model
    elif _LLM_PROVIDER == "hf":
        if not GRADIO_AVAILABLE:
            print("  [lean-export] ERROR: gradio_client not installed. Run: pip install gradio_client")
            return
        _HF_CLIENT = GradioClient(model, token=api_key) if api_key else GradioClient(model)
        if model: _HF_MODEL_NAME = model

def setup_lean_provider(provider, api_key=None, model=None):
    """Configure a separate provider for Lean generation."""
    global _LEAN_PROVIDER, _LEAN_GEMINI_CLIENT, _LEAN_GEMINI_MODEL, _LEAN_OPENAI_CLIENT, _LEAN_OPENAI_MODEL, _LEAN_GROQ_CLIENT, _LEAN_GROQ_MODEL, _LEAN_OLLAMA_MODEL, _LEAN_HF_CLIENT, _LEAN_HF_MODEL
    _LEAN_PROVIDER = provider
    
    if _LEAN_PROVIDER == "gemini":
        _LEAN_GEMINI_CLIENT = genai.Client(api_key=api_key) if api_key else genai.Client()
        _LEAN_GEMINI_MODEL = model
    elif _LEAN_PROVIDER == "openai":
        _LEAN_OPENAI_CLIENT = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()
        _LEAN_OPENAI_MODEL = model
    elif _LEAN_PROVIDER == "groq":
        _LEAN_GROQ_CLIENT = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1") if api_key else openai.OpenAI(base_url="https://api.groq.com/openai/v1")
        _LEAN_GROQ_MODEL = model
    elif _LEAN_PROVIDER == "ollama":
        _LEAN_OLLAMA_MODEL = model
    elif _LEAN_PROVIDER == "hf":
        if not GRADIO_AVAILABLE:
            print("  [lean-export] ERROR: gradio_client not installed. Run: pip install gradio_client")
            return
        _LEAN_HF_CLIENT = GradioClient(model, token=api_key) if api_key else GradioClient(model)
        if model: _LEAN_HF_MODEL = model



# ── Ollama Interface ─────────────────────────────────────────────────────────

def query_ollama(prompt, model="goedel:latest", system_prompt=None, json_mode=False):
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model, 
        "prompt": prompt, 
        "stream": False,
        "options": {
            "num_ctx": 8192, 
            "num_predict": 512,
            "temperature": 0.0,  # Zero temperature for maximum determinism
        }
    }
    if system_prompt:
        data["system"] = system_prompt
    if json_mode and "deepseek" not in model.lower():
        data["format"] = "json"
        
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            resp_text = result.get('response', '').strip()
            # Extract and log thinking if any
            think_match = re.search(r'<think>(.*?)</think>', resp_text, flags=re.DOTALL)
            if think_match:
                think_content = think_match.group(1).strip()
                print(f"  [LLM Think]: {think_content}")
            resp_text = re.sub(r'<think>.*?</think>', '', resp_text, flags=re.DOTALL).strip()
            return resp_text
    except Exception as e:
        print(f"  [lean-export] Ollama error: {e}")
        return ""


_GEMINI_LAST_CALL_TIME = 0.0

def query_gemini(prompt, system_prompt=None, client=None, model=None, json_mode=False):
    """Query Google Gemini API."""
    global _GEMINI_CLIENT, _GEMINI_MODEL_NAME, _GEMINI_LAST_CALL_TIME
    target_client = client or _GEMINI_CLIENT
    target_model = model or _GEMINI_MODEL_NAME
    
    if not target_client:
        print("  [lean-export] Gemini client not initialized!")
        return ""
    
    # Проактивный cooldown (2с)
    elapsed = time.time() - _GEMINI_LAST_CALL_TIME
    if elapsed < 2.0:
        time.sleep(2.0 - elapsed)
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
                response = target_client.models.generate_content(
                    model=target_model,
                    contents=contents,
                    config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=1024)
                )
                return response.text.strip()
            except Exception as e:
                if "429" in str(e):
                    wait_time = 30 + (attempt * 10)
                    print(f"  [gemini] Rate limit hit (429). Sleeping {wait_time}s...")
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
        
        for attempt in range(5):
            try:
                response = target_client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=1024,
                )
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


def query_llm(prompt, model="goedel:latest", system_prompt=None, json_mode=False):
    """Routes to the active LLM provider (ollama, gemini, openai, groq, or hf)."""
    # Use Lean provider if set, otherwise use main provider
    active_provider = _LEAN_PROVIDER or _LLM_PROVIDER
    
    if active_provider == "gemini":
        client = _LEAN_GEMINI_CLIENT or _GEMINI_CLIENT
        model_name = _LEAN_GEMINI_MODEL or _GEMINI_MODEL_NAME or model
        return query_gemini(prompt, system_prompt=system_prompt, client=client, model=model_name, json_mode=json_mode)
    elif active_provider == "openai":
        client = _LEAN_OPENAI_CLIENT or _OPENAI_CLIENT
        model_name = _LEAN_OPENAI_MODEL or _OPENAI_MODEL_NAME or model
        return query_openai(prompt, system_prompt=system_prompt, client=client, model=model_name, json_mode=json_mode)
    elif active_provider == "groq":
        client = _LEAN_GROQ_CLIENT or _GROQ_CLIENT
        model_name = _LEAN_GROQ_MODEL or _GROQ_MODEL_NAME or model
        return query_groq(prompt, system_prompt=system_prompt, client=client, model=model_name, json_mode=json_mode)
    elif active_provider == "hf":
        client = _LEAN_HF_CLIENT or _HF_CLIENT
        model_name = _LEAN_HF_MODEL or _HF_MODEL_NAME or model
        return query_hf(prompt, system_prompt=system_prompt, client=client, model=model_name, json_mode=json_mode)
    else:
        model_name = _LEAN_OLLAMA_MODEL or model
        return query_ollama(prompt, model=model_name, system_prompt=system_prompt, json_mode=json_mode)




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

def translate_to_lean_via_llm(entity_id, entity_type, tex_content, model="goedel:latest", mathlib_hints="", error_feedback=None, previous_code=None):
    """
    Translates LaTeX to Lean 4 using Ollama, supporting error feedback for self-correction.
    """
    tex_clean = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', tex_content, flags=re.DOTALL)
    tex_clean = re.sub(r'^%.*$', '', tex_clean, flags=re.MULTILINE).strip()
    if not tex_clean:
        return ""

    lean_name = entity_id.replace('-', '_')

    system_prompt = """You are an expert in Lean 4 and Mathlib.
Your task is to translate mathematical statements into valid Lean 4 declarations.
RULES:
1. Output ONLY valid Lean 4 code. No markdown formatting, no explanations, no `import` statements.
2. Use Mathlib types: ℝ, ℕ, ℤ, Set, Prop, Type.
3. Axioms: `axiom <name> : <statement>`
4. Theorems: `theorem <name> : <statement> := sorry`
5. Definitions: `def <name> : <type> := sorry`
6. ALL variables must be bound explicitly (∀ or ∃).
7. Do NOT use LaTeX commands (\\forall, \\in, \\mathbb, etc.)."""

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

    response = query_llm(user_prompt, model=model, system_prompt=system_prompt)
    
    # Clean up artifacts
    response = re.sub(r'^```(lean)?\s*', '', response, flags=re.MULTILINE)
    response = re.sub(r'^```\s*$', '', response, flags=re.MULTILINE)
    response = response.strip()
    
    print(f"  [lean-export] Сгенерированный код Lean:\n{response}\n")
    
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
        (r'\\mForall\{([^}]+)\}', r'∀ \1, '),
        (r'\\mExists\{([^}]+)\}', r'∃ \1, '),
        (r'\\mImplies', '→'),
        (r'\\mIff', '↔'),
        (r'\\mDefIff', ':='),
        (r'\\mAnd', '∧'), (r'\\land', '∧'),
        (r'\\mOr', '∨'), (r'\\lor', '∨'),
        (r'\\mNot', '¬'), (r'\\lnot', '¬'),
        (r'\\mIn', '∈'), (r'\\in', '∈'),
        (r'\\mSubset', '⊆'), (r'\\subset', '⊆'),
        (r'\\entityref\{[^}]+\}\{(.*?)\}', r'\1'),
        (r'\\quad', ' '), (r'\\;', ' '),
        (r'\\text\{([^}]+)\}', r'\1'),
        (r'\\left', ''), (r'\\right', ''),
        (r'\\mathbb\{R\}', 'ℝ'), (r'\\mReal', 'ℝ'),
        (r'\\mathbb\{N\}', 'ℕ'), (r'\\mNat', 'ℕ'),
        (r'\\mathbb\{Z\}', 'ℤ'), (r'\\mInt', 'ℤ'),
        (r'\\colon', ':'),
        (r'\\to', '→'),
        (r'\\neq', '≠'),
        (r'\\leq', '≤'), (r'\\le', '≤'),
        (r'\\geq', '≥'), (r'\\ge', '≥'),
        (r'\\forall', '∀'), (r'\\exists', '∃'),
        (r'\\Rightarrow', '→'), (r'\\Leftrightarrow', '↔'),
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
            previous_code=lean_code
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
