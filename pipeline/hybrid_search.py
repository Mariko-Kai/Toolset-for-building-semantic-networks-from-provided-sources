import math
import re
import json
import sys
import io
from typing import List, Tuple, Dict, Any, Optional

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# --- Configuration & Defaults ---
DEFAULT_LOCAL_MODEL = "BAAI/bge-reranker-v2-m3"

# --- Tokenization Commentary for Mathematical Texts (LaTeX) ---
# When processing mathematical textbooks, it is critical to understand how the Tokenizer handles LaTeX:
# 1. Subword Splitting: Math symbols and commands (e.g., \int, \sum, \alpha, \epsilon) are often
#    out-of-vocabulary (OOV) for standard subword tokenizers trained on natural language.
#    They get aggressively split into individual characters or subwords (e.g., '\', 'alpha').
# 2. Structural Punctuation: Punctuation commonly used in LaTeX (e.g., '_', '^', '{', '}', '\')
#    are treated as distinct tokens, which introduces massive token overhead.
# 3. Context Inflation: An equation that looks visually compact (e.g., \int_a^b f(x) dx) might
#    consume 2-3x more tokens than an equivalent natural language sentence.
# 4. Truncation Safety: When feeding pages into a Reranker (Cross-Encoder), we MUST use a very large
#    max_length (e.g., 8192 for BGE-M3 or GTE-Multilingual) to avoid truncating vital mathematical
#    proofs and definitions. Setting `truncation=True` and `padding=True` ensures that we safely
#    use the maximum context window without crashing on exceptionally dense LaTeX pages.
# ------------------------------------------------------------------

class BM25Retriever:
    """
    Stage 1: Lightweight Lexical Retriever using BM25 (Okapi) algorithm.
    Filters candidate pages quickly without heavy dependencies (e.g., no need for rank_bm25).
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths: List[int] = []
        self.avgdl: float = 0.0
        self.df: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_freqs: List[Dict[str, int]] = []
        self.corpus_size: int = 0
        self.pages: List[Tuple[int, str]] = []

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenizer that extracts alphanumeric sequences (Cyrillic & Latin)."""
        text = text.lower()
        return re.findall(r'(?u)\b\w+\b', text)

    def fit(self, pages: List[Tuple[int, str]]) -> None:
        """Indexes the list of textbook pages."""
        self.pages = pages
        self.corpus_size = len(pages)
        total_length = 0

        for _, text in pages:
            tokens = self._tokenize(text)
            length = len(tokens)
            self.doc_lengths.append(length)
            total_length += length

            freq_dict: Dict[str, int] = {}
            for token in tokens:
                freq_dict[token] = freq_dict.get(token, 0) + 1

            self.doc_freqs.append(freq_dict)

            for token in freq_dict.keys():
                self.df[token] = self.df.get(token, 0) + 1

        self.avgdl = total_length / self.corpus_size if self.corpus_size > 0 else 0.0

        # Precompute IDF scores
        for token, df in self.df.items():
            # BM25 IDF formula
            idf_score = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1.0)
            self.idf[token] = idf_score

    def get_scores(self, query: str) -> List[float]:
        """Calculates BM25 scores for all documents given a query."""
        query_tokens = self._tokenize(query)
        scores = [0.0] * self.corpus_size

        for i, doc_freq in enumerate(self.doc_freqs):
            score = 0.0
            doc_len = self.doc_lengths[i]
            for token in query_tokens:
                if token not in doc_freq:
                    continue
                tf = doc_freq[token]
                idf = self.idf.get(token, 0.0)
                # BM25 Term Frequency weighting
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / self.avgdl))
                score += idf * (numerator / denominator)
            scores[i] = score

        return scores

    def search(self, query: str, top_k: int = 20) -> List[Tuple[int, str]]:
        """Returns the top_k most relevant pages based on BM25 scores."""
        if not self.pages:
            return []
        scores = self.get_scores(query)
        scored_pages = [(score, self.pages[i]) for i, score in enumerate(scores)]
        # Sort by score descending
        scored_pages.sort(key=lambda x: x[0], reverse=True)
        # Extract the (page_num, text) payload
        return [page for score, page in scored_pages[:top_k]]


class CrossEncoderReranker:
    """
    Stage 2: Semantic Reranker using a Cross-Encoder model.
    Accepts [query, document] pairs. Supports local Hugging Face `transformers` execution and REST API calls.
    """
    def __init__(self, backend: str = "local", model_name: str = DEFAULT_LOCAL_MODEL, api_url: Optional[str] = None):
        self.backend = backend.lower()
        self.model_name = model_name
        self.api_url = api_url
        self.tokenizer = None
        self.model = None

        if self.backend == "local":
            self._init_local_model()

    def _init_local_model(self) -> None:
        """Initializes the local Hugging Face transformers model."""
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
        except ImportError:
            raise ImportError("Please install `torch` and `transformers` to use the 'local' backend.")

        print(f"[Reranker] Loading local model '{self.model_name}'...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name).to(self.device)
        self.model.eval()

    def rerank(self, query: str, documents: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
        """
        Reranks a list of candidate documents against the query.
        Returns a sorted list of dictionaries with page_num, score, and text_snippet.
        """
        if not documents:
            return []

        if self.backend == "local":
            return self._rerank_local(query, documents)
        elif self.backend == "rest":
            return self._rerank_rest(query, documents)
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

    def _rerank_local(self, query: str, documents: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
        """Executes reranking using the local Hugging Face model."""
        import torch

        print(f"[Reranker] Running local Hugging Face model inference on {len(documents)} candidates...", flush=True)
        # Cross-Encoders expect input as a list of [query, text] pairs
        pairs = [[query, text] for _, text in documents]

        # Max length is typically 8192 for modern mathematical rerankers (e.g., BGE-M3).
        max_len = 8192
        inputs = self.tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=max_len,
            return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits.squeeze(-1) # Shape: (batch_size,)

            # Apply sigmoid to convert raw logits to probabilities [0, 1]
            if len(logits.shape) == 0:
                # Handle batch_size = 1 case
                scores = [torch.sigmoid(logits).item()]
            else:
                scores = torch.sigmoid(logits).tolist()

        results = []
        for i, (page_num, text) in enumerate(documents):
            results.append({
                "page_num": page_num,
                "score": scores[i],
                "text_snippet": text[:1000] # Provide snippet for context
            })

        # Sort descending by score
        results.sort(key=lambda x: x["score"], reverse=True)

        print("[Reranker] Local Reranking completed. Top matches:", flush=True)
        for res in results[:3]:
            print(f"  -> Page {res['page_num']}: Score {res['score']:.4f} ('{res['text_snippet'][:50]}...')", flush=True)

        return results

    def _rerank_rest(self, query: str, documents: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
        """Executes reranking via a REST API endpoint (e.g., local llama.cpp server).

        This method is resilient: it will try multiple common endpoint paths (original api_url,
        /v1/rerank and /rerank on the same host) to accommodate different local server implementations.
        """
        if not self.api_url:
            raise ValueError("api_url must be provided when using the 'rest' backend.")

        print(f"[Reranker] Sending HTTP request to REST API: {self.api_url} (candidates: {len(documents)})...", flush=True)
        # Prepare documents as simple text array for the API
        texts = [text for _, text in documents]
        payload = {
            "query": query,
            "documents": texts
        }

        # Build a list of endpoints to try (original + common fallbacks on same host)
        endpoints = [self.api_url]
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(self.api_url)
            if parsed.scheme and parsed.hostname:
                base = f"{parsed.scheme}://{parsed.hostname}"
                if parsed.port:
                    base = f"{base}:{parsed.port}"
                for p in ["/v1/rerank", "/rerank"]:
                    candidate = base + p
                    if candidate not in endpoints:
                        endpoints.append(candidate)
        except Exception:
            # If parsing fails, just try the original api_url
            pass

        last_error = None
        for url in endpoints:
            try:
                req = urllib.request.Request(
                    url,
                    json.dumps(payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )
                with urllib.request.urlopen(req, timeout=600) as response:
                    result = json.loads(response.read().decode('utf-8'))

                    # Assume standard API response: {"results": [{"index": 0, "score": 0.9}, ...]}
                    api_results = result.get("results", [])
                    print(f"[Reranker] REST API returned {len(api_results)} scoring results from {url}.", flush=True)

                    formatted_results = []
                    for item in api_results:
                        idx = item.get("index")
                        score = item.get("score")

                        if idx is None or score is None:
                            continue

                        # Apply manual sigmoid if the API returns raw logits outside [0, 1]
                        try:
                            if score > 1.0 or score < 0.0:
                                score = 1.0 / (1.0 + math.exp(-score))
                        except Exception:
                            # If score is not numeric, skip
                            continue

                        formatted_results.append({
                            "page_num": documents[idx][0],
                            "score": score,
                            "text_snippet": documents[idx][1][:1000]
                        })

                    formatted_results.sort(key=lambda x: x["score"], reverse=True)

                    print("[Reranker] REST API Reranking completed. Top matches:", flush=True)
                    for res in formatted_results[:3]:
                        print(f"  -> Page {res['page_num']}: Score {res['score']:.4f} ('{res['text_snippet'][:50]}...')", flush=True)

                    return formatted_results
            except Exception as e:
                # Prefer to continue trying other endpoints on 404 / not found
                print(f"[Reranker] API Error contacting {url}: {e}", flush=True)
                last_error = e
                # If 404, try next candidate; otherwise also try next candidate but log
                continue

        # If we reach here, all endpoints failed
        if last_error:
            print(f"[Reranker] All endpoint attempts failed. Last error: {last_error}", flush=True)
        return []


# --- Query Builder ---
def build_rerank_query(term: str, entity_type: str) -> str:
    """
    Stage 3 Helper: Enhances the search query based on the mathematical entity type
    to provide explicit structural context to the Cross-Encoder.
    """
    entity_type = entity_type.lower().strip()

    # Detect if the query term contains Russian (Cyrillic) characters
    is_ru = bool(re.search(r'[\u0400-\u04FF]', term))

    if is_ru:
        if entity_type == "definition":
            return f"Определение понятия {term}"
        elif entity_type == "theorem":
            return f"Формулировка и доказательство теоремы {term}"
        elif entity_type == "property":
            return f"Свойства и признаки {term}"
        else:
            return term
    else:
        if entity_type == "definition":
            return f"Definition of {term}"
        elif entity_type == "theorem":
            return f"Theorem and proof of {term}"
        elif entity_type == "property":
            return f"Properties of {term}"
        else:
            return term


# --- Main Flow Orchestrator ---
class HybridSearchPipeline:
    """
    Orchestrator coordinating the Lexical Retriever and Cross-Encoder Reranker.
    Supports context management to start and stop a local llama.cpp server.
    """
    def __init__(
        self,
        backend: str = "local",
        model_name: str = DEFAULT_LOCAL_MODEL,
        api_url: Optional[str] = None,
        server_model_path: Optional[str] = None,
        server_port: int = 8080
    ):
        self.backend = backend.lower()
        self.model_name = model_name
        self.api_url = api_url
        self.server_model_path = server_model_path
        self.server_port = server_port
        self.server_process = None

        # Start the local server if requested and not already running
        if self.backend == "rest" and self.server_model_path and self.api_url:
            self._ensure_server_running()

        self.retriever = BM25Retriever()
        self.reranker = CrossEncoderReranker(backend=self.backend, model_name=self.model_name, api_url=self.api_url)

    def _ensure_server_running(self):
        """Checks if the server at self.api_url is responsive. If not, spawns it."""
        import urllib.parse
        import subprocess
        import sys
        import time
        import socket

        url_parsed = urllib.parse.urlparse(self.api_url)
        host = url_parsed.hostname or "localhost"
        port = url_parsed.port or self.server_port

        def is_port_open():
            try:
                with socket.create_connection((host, port), timeout=0.3):
                    return True
            except Exception:
                return False

        # Test if server is already running by checking the port
        print(f"[HybridSearch] Checking if server port {port} is already open...", flush=True)
        if is_port_open():
            print(f"[HybridSearch] Found active server at {self.api_url} (port {port} is open). Reusing it.", flush=True)
            return

        print(f"[HybridSearch] Port {port} is closed. Starting local llama.cpp server for '{self.server_model_path}' on port {port}...", flush=True)

        # Configure env variables to avoid Windows console Unicode errors on start
        env = dict(subprocess.os.environ)
        env["PYTHONIOENCODING"] = "utf-8"

        cmd = [
            sys.executable,
            "-m", "llama_cpp.server",
            "--model", self.server_model_path,
            "--port", str(port),
            "--embedding", "True"
        ]

        try:
            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env
            )
        except Exception as e:
            raise RuntimeError(f"Failed to start llama.cpp server subprocess: {e}")

        # Poll the server until it responds or timeout occurs (20 seconds)
        print("[HybridSearch] Subprocess spawned. Waiting for server to become responsive...", flush=True)
        start_time = time.time()
        timeout = 20.0
        server_ready = False

        while time.time() - start_time < timeout:
            elapsed = time.time() - start_time
            print(f"[HybridSearch] Ping port {port}... (elapsed: {elapsed:.1f}s)", flush=True)
            if self.server_process.poll() is not None:
                # Process terminated early
                raise RuntimeError(f"llama.cpp server process exited prematurely with code {self.server_process.returncode}.")

            if is_port_open():
                print(f"[HybridSearch] Port {port} responded! Giving FastAPI 1.0s to initialize routes...", flush=True)
                time.sleep(1.0)
                server_ready = True
                break
            else:
                time.sleep(0.5)

        if not server_ready:
            self.close()
            raise TimeoutError(f"llama.cpp server did not respond at {self.api_url} within {timeout} seconds.")

        print("[HybridSearch] Local llama.cpp server started successfully and is responsive!", flush=True)

    def close(self):
        """Terminates the spawned local llama.cpp server process if it exists."""
        if self.server_process:
            print("[HybridSearch] Terminating local llama.cpp server process...", flush=True)
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except Exception:
                try:
                    self.server_process.kill()
                except Exception:
                    pass
            self.server_process = None
            print("[HybridSearch] Local llama.cpp server stopped.", flush=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _clean_text(self, text: str) -> str:
        """Cleans OCR artifacts and normalizes spacing."""
        # Remove hyphenations at the end of lines
        text = re.sub(r'-\s*\n\s*', '', text)
        # Replace newlines with spaces
        text = text.replace('\n', ' ')
        # Remove multiple consecutive spaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def search(self, term: str, entity_type: str, pages: List[Tuple[int, str]], top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Executes the two-stage hybrid search pipeline.
        `pages` format: [(page_num, "page text"), ...]
        """
        if not pages:
            return []

        # Step 1: Clean texts
        print(f"[HybridSearch] Stage 1: Normalizing math LaTeX texts for {len(pages)} pages...", flush=True)
        cleaned_pages = [(page_num, self._clean_text(text)) for page_num, text in pages]

        # Step 2: Lexical Retrieval (Stage 1) - Fast Top-20 selection
        print(f"[HybridSearch] Fitting Okapi BM25 Index on {len(cleaned_pages)} pages...", flush=True)
        self.retriever.fit(cleaned_pages)
        # Use raw term for Stage 1 BM25 to ensure broad recall
        print(f"[HybridSearch] Running BM25 scoring for query term '{term}'...", flush=True)
        candidate_pages = self.retriever.search(term, top_k=20)

        if not candidate_pages:
            print("[HybridSearch] No candidate pages found in Lexical Retrieval.", flush=True)
            return []

        print(f"[HybridSearch] Stage 1 BM25 retrieved {len(candidate_pages)} candidate pages: {[p[0] for p in candidate_pages]}", flush=True)

        # Step 3: Query Generation for Semantic Search
        extended_query = build_rerank_query(term, entity_type)
        print(f"[HybridSearch] Stage 2: Entity type is '{entity_type}'. Structural Query -> '{extended_query}'", flush=True)

        # Step 4: Cross-Encoder Reranking (Stage 2)
        reranked_results = self.reranker.rerank(extended_query, candidate_pages)

        # Step 5: Threshold Filtering
        # Apply a strict threshold of >= 0.5 probability
        print(f"[HybridSearch] Filtering {len(reranked_results)} scored results using threshold >= 0.5...", flush=True)
        filtered_results = [res for res in reranked_results if res["score"] >= 0.5]

        # If thresholding removes everything, fallback to highest absolute scores gracefully
        # if not filtered_results and reranked_results:
        #     print("[HybridSearch] Warning: All results fell below 0.5. Falling back to highest scored candidates.", flush=True)
        #     filtered_results = reranked_results

        final_top = filtered_results[:top_k]

        print(f"[HybridSearch] Complete! Selected Top-{len(final_top)} pages: {[res['page_num'] for res in final_top]}", flush=True)
        return final_top


if __name__ == "__main__":
    # Simple CLI Test Harness
    print("Initializing HybridSearchPipeline in REST API mock mode for testing...")

    # We use a mocked 'rest' backend here to avoid downloading the huggingface model during simple testing
    class MockCrossEncoderReranker(CrossEncoderReranker):
        def _rerank_rest(self, query: str, documents: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
            # Mocking the REST API response for testing
            results = []
            for i, (page_num, text) in enumerate(documents):
                # Fake score generation: if the exact query term appears, give a high score
                score = 0.9 if "Интеграл Дарбу" in text else 0.1
                results.append({
                    "page_num": page_num,
                    "score": score,
                    "text_snippet": text[:100]
                })
            results.sort(key=lambda x: x["score"], reverse=True)
            return results

    pipeline = HybridSearchPipeline(backend="rest", api_url="http://dummy")
    # Override with mock for test
    pipeline.reranker = MockCrossEncoderReranker(backend="rest", api_url="http://dummy")

    dummy_pages = [
        (1, "Здесь начинается глава про производные. Производная функции..."),
        (2, "Интеграл Римана определяется как предел интегральных сумм..."),
        (3, "Определение понятия Интеграл Дарбу. Верхний и нижний интегралы Дарбу-\n"
            "являются ключевыми концепциями..."),
        (4, "Просто случайная страница без полезной информации о матанализе."),
        (5, "Свойства Интеграла Дарбу: если функция интегрируема...")
    ]

    test_term = "Интеграл Дарбу"
    test_type = "definition"

    print(f"\n--- Testing Search for: '{test_term}' (Type: {test_type}) ---")
    results = pipeline.search(test_term, test_type, dummy_pages, top_k=2)

    for i, res in enumerate(results, 1):
        print(f"\nResult {i}:")
        print(f"Page: {res['page_num']}")
        print(f"Score: {res['score']:.4f}")
        print(f"Snippet: {res['text_snippet']}...")
