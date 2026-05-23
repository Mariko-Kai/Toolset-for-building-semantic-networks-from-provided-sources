import os
import json
import time
import urllib.request
import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

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
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
        pass
        
    @abstractmethod
    def get_embedding(self, text: str) -> Optional[List[float]]:
        pass


class OllamaStrategy(ModelStrategy):
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
        model = self.model_name or "qwen2.5:14b"
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "top_p": 0.9,
                "num_ctx": 8192
            }
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                ans = result.get("response", "")
                think_match = re.search(r'<think>(.*?)</think>', ans, re.DOTALL)
                if think_match:
                    log_think(think_match.group(1).strip())
                    ans = re.sub(r'<think>.*?</think>', '', ans, flags=re.DOTALL).strip()
                return ans
        except Exception as e:
            print(f"[OllamaStrategy] Error: {e}")
            return ""
            
    def get_embedding(self, text: str) -> Optional[List[float]]:
        model = "nomic-embed-text:latest"
        url = "http://localhost:11434/api/embeddings"
        payload = {
            "model": model,
            "prompt": text
        }
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'))
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get("embedding")
        except Exception as e:
            print(f"[OllamaStrategy] Embedding error: {e}")
            return None


class GeminiStrategy(ModelStrategy):
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
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
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
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
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = False) -> str:
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

    def query_llm(self, prompt: str, model: Optional[str] = None, json_mode: bool = False, provider: Optional[str] = None, system_prompt: Optional[str] = None) -> str:
        # Determine the role dynamically or just use an ad-hoc strategy if provider is explicitly passed
        if provider:
            strategy = ModelFactory.create_strategy(provider, model)
        else:
            strategy = self.strategies.get("main")
            if not strategy:
                return ""
        return strategy.generate_content(prompt, system_prompt, json_mode)
        
    def get_embedding(self, text: str, provider: Optional[str] = None, model: Optional[str] = None) -> Optional[List[float]]:
        if provider:
            strategy = ModelFactory.create_strategy(provider, model)
        else:
            strategy = self.strategies.get("main")
            if not strategy:
                return None
        return strategy.get_embedding(text)
