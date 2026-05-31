# Mathesis — Neuro-Symbolic Mathematical Knowledge Formalization Pipeline

## 1. Project Purpose

**Mathesis** is a software pipeline for automated extraction, canonization, and formal verification of mathematical knowledge found in educational textbooks. The system solves three interconnected problems:

1. **Extraction:** Formulations of mathematical entities (definitions and propositions) are extracted from a corpus of textbooks (PDFs), preserving provenance (source, page).
2. **Canonization:** Extracted formulations are clustered, deduplicated, and synthesized into a strict canonical LaTeX format, building a unified knowledge graph.
3. **Formalization:** Each proposition is translated into Lean 4 code and verified by the compiler backed by the Mathlib library, ensuring mathematical soundness.

The pipeline outputs a **typed dependency graph** where every theorem or proposition is traced back to foundational axioms (Zermelo-Fraenkel set theory, ZFC). The knowledge axis is strictly binary and mirrors Lean's type system: every entity is either a definition (`def`) or a proposition (`prop`). Axioms are represented as `prop` with the metadata `lean_decl = 'axiom'`.

The architecture is **neuro-symbolic**: generative models (LLMs) extract and translate text, while the symbolic layer (SQLite graph and the Lean compiler) guarantees consistency and formal correctness.

---

## 2. System Requirements

| Component | Purpose | Requirement |
|---|---|---|
| Python ≥ 3.10 | Runtime environment | Mandatory |
| Core Dependencies (`requirements.txt`) | Web interface & database core | Mandatory |
| AI/ML Expansion (`.[ai]`) | PDF extraction, embeddings, LLM providers | Mandatory for pipeline |
| LaTeX Distribution (TeX Live / MiKTeX) | PDF document compilation | For PDF generation |
| Lean 4 (`elan` / `lake`) + Mathlib | Formal verification | For Lean validation |
| Ollama / Cloud API Keys | LLM access | Mandatory for pipeline |
| `llama-cpp-python` (built with CUDA) | Cross-encoder page reranker | Optional (has lexical fallback) |

Supported model providers: `ollama`, `gemini`, `openai`, `groq`, `hf`, `llama_cpp`.

---

## 3. Installation & Configuration

### 3.1. Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3.2. Installing Dependencies

Minimal installation (web interface and read-only database catalog):
```bash
pip install -r requirements.txt
```

Full installation (PDF extraction, embeddings, and LLM orchestration):
```bash
pip install -e .[ai]
```

Development tools (testing, linting, type-checking):
```bash
pip install -e .[dev]
```

### 3.3. Provider & Key Configuration

API keys and default settings can be configured using environment variables or a configuration JSON. The environment variables in `.env` take absolute priority and will not be overwritten.

1. **`.env` File** (loaded automatically when importing `pipeline.config`):
   ```dotenv
   GEMINI_API_KEY=your_gemini_key
   OPENAI_API_KEY=your_openai_key
   GROQ_API_KEY=your_groq_key
   ```
2. **`api_config.json` File** (managed by the web application; contains `api_keys`, `providers`, and `models` partitioned by modules).

The system resolves configurations using the following **strict descending priority**:
$$\text{CLI Global} \longrightarrow \text{CLI Module} \longrightarrow \text{Environment Variable Module} \longrightarrow \text{api\_config.json} \longrightarrow \text{config.py Defaults}$$

### 3.4. Database Initialization

The canonical knowledge database is stored at `db/mathesis_index.db` (can be overridden with `MATHESIS_DB_PATH`). Initialize an empty schema with:
```bash
python pipeline/init_db.py
```

The database schema is version-controlled (`SCHEMA_VERSION = 3`). When opening an older database, an **idempotent migration** runs automatically, adding missing columns to the flat `entities` table to guarantee backward compatibility.

---

## 4. Running Modules

All commands should be executed from the project root directory.

### 4.1. Web Interface

An interactive catalog of mathematical entities, LaTeX PDF compiler, and run monitoring dashboard:
```bash
uvicorn web.app:app --reload
```
Once started, the catalog is available at `http://127.0.0.1:8000`.

Key routes:

| Route | Purpose |
|---|---|
| `GET /` | Homepage: select entities and compile LaTeX PDF |
| `GET /catalog` | Catalog of entities grouped by kind (definitions, propositions) |
| `GET /entity/{id}` | Detailed entity card with formula rendering via KaTeX |
| `GET /monitor` | Pipeline monitor: recent runs and active incidents |
| `GET /monitor/{run_id}` | Detailed event timeline for a specific pipeline run |
| `GET /api/runs`, `GET /api/runs/{run_id}` | Programmatic access to run states (JSON) |
| `POST /api/incidents/{id}/resolve` | Resolve a pipeline incident (`confirmed` / `rejected` / `applied`) |
| `WebSocket /ws/compiler` | Real-time compilation and search status synchronization |

If `tools/cloudflared.exe` is present in the workspace, the web app automatically establishes a secure public tunnel for remote demonstration.

### 4.2. Main Enrichment Coordinator

The [`pipeline/enrichment_coordinator.py`](pipeline/enrichment_coordinator.py) script is the main entry point. Given a natural language query, it checks if the entity exists in the database. If not, it executes the entire enrichment pipeline (extraction → alignment → synthesis → formalization) with recursive dependency resolution.

The coordinator supports **independent module-level model routing**: provider (`--*-provider`), model (`--*-model`), and API key (`--*-api-key`) can be configured separately for each stage. This allows using advanced cloud models for synthesis and fast local models for extraction or embedding.

Basic run (using defaults):
```bash
python pipeline/enrichment_coordinator.py "Cauchys mean value theorem"
```

Orchestrated run (with persistent run tracking and incident reporting):
```bash
python pipeline/enrichment_coordinator.py "Cauchys mean value theorem" --orchestrated
```

Hybrid routing example:
```bash
python pipeline/enrichment_coordinator.py "Definition of uniformly continuous function" \
  --cv-model qwen3-vl:4b \
  --extract-preview-provider llama_cpp \
  --extract-preview-model "bge-reranker-v2-m3-Q6_K.gguf" \
  --extract-provider gemini   --extract-model gemini-2.5-flash \
  --synth-provider   gemini   --synth-model   gemini-2.5-flash \
  --lean-provider    ollama   --lean-model    "goedel:latest" \
  --embed-provider   ollama   --embed-model   "nomic-embed-text:latest"
```

Logical modules and CLI option prefixes:

| Prefix | Module | Purpose |
|---|---|---|
| `--provider/--model/--api-key` | Global | Default fallback for all modules |
| `--extract-*` | Extraction | PDF text reading and raw formulation parsing |
| `--extract-preview-*` | Preview | Rapid page pre-filtering (reranking or lightweight LLM) |
| `--synth-*` | Synthesis | Canonical LaTeX drafting, deduplication, and source merging |
| `--lean-*` | Formalization | Lean 4 theorem formulation and verification |
| `--embed-*` | Embeddings | Vector-based entity mapping and dependency resolution |
| `--cv-model` | Vision/OCR | Multimodal LaTeX formula extraction from PDF pages |

Control flags:

* `--orchestrated` — executes under the agentic orchestrator, persisting run history (equivalent to setting `MATHESIS_ORCHESTRATED=1`).
* `--no-validate` — skips Lean compilation (useful for rapid LaTeX catalog debugging).
* `--force-refresh` — clears the cache and forces fresh extraction.
* `--ocr-pages '{"book": "zorich", "pages": [212, 214]}'` — bypasses search and processes only the specified pages.

### 4.3. Cross-Encoder Page Reranker (llama-cpp-python, GGUF)

The preview stage defaults to an **in-process** `bge-reranker-v2-m3` cross-encoder model via `llama-cpp-python` (with GPU layer offloading). The reranker sorts matching candidate pages, drastically improving accuracy compared to simple lexical search. The GGUF model is automatically loaded from the `llama/` folder or the path in `MATHESIS_LLAMA_DIR`.

To build `llama-cpp-python` with CUDA and reranker support, execute:
```bash
pip install ninja
CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=75" pip install --no-cache-dir llama-cpp-python
```
*(Specify `CMAKE_CUDA_ARCHITECTURES` matching your GPU compute capability, e.g. 75 for Turing).*

The number of layers offloaded to the GPU can be customized via `MATHESIS_RERANK_GPU_LAYERS` (defaults to `-1` for all layers). If the package or model is missing, the system gracefully falls back to basic lexical BM25 search.

### 4.4. Running Specific Pipeline Stages

For debugging or targeted re-processing, stages can be run independently:

```bash
# Extract raw formulations from all PDFs in Books/ (ru|en query format)
python pipeline/ensemble_extractor.py "cauchys mean value theorem"

# Align and cluster extracted raw formulations semantically
python pipeline/entity_aligner.py

# Synthesize LaTeX and validate Lean for a specific term
python pipeline/canonical_synthesizer.py --canonical-term "cauchys mean value theorem"
```

### 4.5. LaTeX PDF Compilation

Compilation requires a working local LaTeX installation.

```bash
# Compile PDF for a specific root entity (automatically resolves and appends dependencies)
python pipeline/generate_answer.py --roots "prop-cauchys-mean-value-theorem"
# Output path: output/result.pdf

# Compile a full mathematical textbook containing all database entities
python pipeline/generate_full_book.py
# Output path: output/full_book.pdf
```
Use `--no-enrich` to skip auto-synthesis of missing dependencies, and `--no-validate` to skip Lean validation.

### 4.6. Lean 4 Formal Verification

Requires a working Lean toolchain (`elan`/`lake`) and a pre-built `lean_validator` project containing Mathlib and `repl`. The REPL runs persistently in the background: Mathlib is loaded into RAM once (prewarmed under a `MATHESIS_LEAN_WARMUP_TIMEOUT` budget, default 600s), enabling individual validation requests to compile in milliseconds. Prewarming executes asynchronously during the early extraction phases. The individual elaboration timeout (`MATHESIS_LEAN_TIMEOUT`, default 300s) applies strictly to the target declaration.

```bash
# Translate the database graph to Lean 4 (--force rebuilds all validated files)
python pipeline/export_to_lean.py --lean-provider ollama --lean-model goedel:latest

# Validate a specific standalone .lean file
python pipeline/lean_validator.py lean_validator/Validated/prop-cauchys-mean-value-theorem.lean

# Check formal mathematical equivalence between two database definitions
python pipeline/lean_equivalence_checker.py prop-rolle prop-rolle-dup
```

### 4.7. Database & Graph Maintenance

```bash
# Rebuild canonical SQLite index from content/*.tex without calculating embeddings (fast)
python pipeline/reseed_db.py

# Actualize SQLite database entries after manual edits to .tex files in content/
python pipeline/actualize_db.py

# Recalculate vector embeddings for entities (--force updates all)
python pipeline/update_embeddings.py

# Perform semantic deduplication and merge equivalent entities verified by Lean
python pipeline/postprocess_equivalence.py   # use --dry-run for dry execution

# Generate project LaTeX macros (mathesis_macros.sty) from entity headers in content/
python pipeline/generate_macros.py

# Search terms in the ranked textbook corpus
python pipeline/search_index.py --query "uniform continuity"
```

### 4.8. CLI Run Monitoring

```bash
python pipeline/monitor.py                       # Lists recent orchestrator runs
python pipeline/monitor.py <run_id>              # Details event log for a run
python pipeline/monitor.py --incidents           # Lists active incidents
python pipeline/monitor.py --resolve <id> --as confirmed
```

---

## 5. Default Model Configuration

Default providers and models configured in [`pipeline/config.py`](pipeline/config.py):

| Module | Default Provider | Default Model | Configurable Environment Override |
|---|---|---|---|
| `extract` | `ollama` | `qwen3:8b` | `MATHESIS_EXTRACT_MODEL` |
| `preview` | `llama_cpp` | `bge-reranker-v2-m3-Q6_K.gguf` | `MATHESIS_PREVIEW_MODEL` |
| `synth` | `ollama` | `qwen3:8b` | `MATHESIS_SYNTH_MODEL` |
| `lean` | `ollama` | `goedel:latest` | `MATHESIS_LEAN_MODEL` |
| `embed` | `ollama` | `nomic-embed-text:latest` | `MATHESIS_EMBED_MODEL` |

### Provider-Specific Defaults
* **Ollama (local):** Falls back to `"deepseek-r1:7b"` as the main model if not explicitly specified.
* **Gemini (cloud):** `gemini-2.5-flash`
* **OpenAI (cloud):** `gpt-4o-mini`
* **Groq (cloud):** `llama-3.3-70b-versatile`

---

## 6. Environment Variables

All settings can be placed in your local `.env` file:

| Variable | Description | Default |
|---|---|---|
| `MATHESIS_DB_PATH` | Path to the canonical SQLite database index | `db/mathesis_index.db` |
| `MATHESIS_ORCHESTRATED` | Run the coordinator under agentic orchestrator tracking | `0` (disabled) |
| `MATHESIS_LLAMA_DIR` | Directory containing GGUF reranker models | Project `llama/` folder |
| `MATHESIS_RERANK_GPU_LAYERS` | GPU layers offloaded to CUDA for reranking | `-1` (all layers) |
| `MATHESIS_LEAN_TIMEOUT` | Timeout budget for individual Lean elaboration (seconds) | `300` |
| `MATHESIS_LEAN_WARMUP_TIMEOUT` | Timeout budget for loading Mathlib into REPL RAM (seconds) | `600` |
| `MATHESIS_OLLAMA_MODEL` | Default model for local Ollama strategies | `deepseek-r1:7b` |
| `MATHESIS_GEMINI_MODEL` | Default model for Gemini strategies | `gemini-2.5-flash` |
| `MATHESIS_OPENAI_MODEL` | Default model for OpenAI strategies | `gpt-4o-mini` |
| `MATHESIS_GROQ_MODEL` | Default model for Groq strategies | `llama-3.3-70b-versatile` |
| `GEMINI_API_KEY` | API Key for Google Gemini | (None) |
| `OPENAI_API_KEY` | API Key for OpenAI | (None) |
| `GROQ_API_KEY` | API Key for Groq | (None) |

---

## 7. Project Structure

```
.
├── web/                     FastAPI Web Application (catalog, compiler, monitor)
│   ├── app.py               App entry point and route endpoints
│   ├── templates/           Jinja2 templates
│   └── static/              Styles and static assets
├── pipeline/                Neuro-symbolic execution pipeline
│   ├── enrichment_coordinator.py Main orchestration entry point
│   ├── ensemble_extractor.py    PDF text raw parser
│   ├── hybrid_search.py         BM25 + llama-cpp-python Cross-Encoder reranking
│   ├── canonical_synthesizer.py LaTeX compiler and Lean 4 loop validation
│   ├── export_to_lean.py        Translates content graph to Lean 4 code
│   ├── orchestration/           Incidents, run logger, and run state persistency
│   └── nodes/                   Process adapters (OCR, subprocesses)
├── mathesis/                Core Database access layer (Facade API)
│   ├── schema.py            Canonical SQLite DDL
│   ├── db.py                Connection, schema init, and migrations
│   ├── repo.py / core.py    Repository patterns and Facade class
│   └── models.py            Typed structures for entities and relations
├── content/                 LaTeX mathematical knowledge files
├── Books/                   Corpus of textbooks (PDFs) for extraction
├── llama/                   Local GGUF files (reranker, offline agents)
├── lean_validator/          Lean 4 verification project (Mathlib, repl)
├── db/                      Active SQLite index storage folder
├── output/                  Target output directory for compiled PDFs
├── docs/                    Technical architecture and developer guides
└── tests/                   Pytest suite folder
```

---

## 8. Testing

Run the test suites using `pytest`:
```bash
pytest
```
Tests are isolated from active workspace assets and use a separate test database configured by `MATHESIS_DB_PATH`.

---

## 9. Developer Guides

Detailed technical guidelines are available in `docs/`:

* [System Deployment](docs/howto/deployment.md) — Step-by-step setup manual.
* [Architecture Design](docs/architecture/design.md) — Entities classification and graph rules.
* [Agentic Orchestrator](docs/architecture/agentic_orchestrator.md) — Run tracking, incidents logging, and human-in-the-loop resolutions.
* [Code Conventions](docs/devguide/structure.md) — Formatting and programming guidelines.
