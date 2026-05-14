# Architecture & Design

## 1. Formal Entity-Relationship Model

### 1.1 Logical Model (Entities)

```mermaid
erDiagram
    AXIOM {
        string id PK "e.g. axm-zfc-choice"
        string name "Axiom of Choice"
        string system "ZFC | FOL | Tool"
        text statement "LaTeX"
    }

    OBJECT {
        string id PK "e.g. obj-sequence"
        string name "Sequence"
        text aliases "JSON array"
        string module "e.g. analysis"
        text formal_definition "LaTeX"
        text intuition "LaTeX"
    }

    PROPERTY {
        string id PK "e.g. prop-bounded"
        string name "Bounded"
        text aliases "JSON array"
        string module "e.g. analysis"
        text formal_definition "LaTeX"
        text equivalent_forms "LaTeX, optional"
    }

    OPERATION {
        string id PK "e.g. op-addition"
        string name "Addition"
        text aliases "JSON array"
        string module "e.g. algebra"
        int arity "1, 2, ..."
        text formal_definition "LaTeX"
        string codomain_id FK "result object type"
    }

    OPERATION_ARGUMENT {
        string operation_id FK,PK
        int position PK "0, 1, 2, ..."
        string object_id FK
        string role "operand | parameter"
    }

    THEOREM {
        string id PK "e.g. thm-bolzano-weierstrass"
        string name "Bolzano-Weierstrass"
        string subtype "theorem | lemma"
        string parent_theorem_id FK "NOT NULL for lemmas"
        string module "e.g. analysis"
        text statement "LaTeX"
        text proof "LaTeX, full"
        text strategy "proof method summary"
    }

    OBJECT_PROPERTY {
        int id PK "surrogate"
        string object_id FK
        string property_id FK
        text context "LaTeX, nullable"
        string context_ref FK "nullable, obj-id"
    }

    THEOREM_DEPENDENCY {
        string theorem_id FK,PK "who uses"
        string used_thm_id FK,PK "what is used"
        string proof_step "e.g. Step 3"
    }

    EQUIVALENCE {
        string entity_a_id FK,PK "a_id < b_id"
        string entity_b_id FK,PK
        string proof_id FK "thm proving A iff B"
    }

    OBJECT_COMPOSITION {
        string container_id FK
        string obj_comp_id FK "nullable, object"
        string prop_comp_id FK "nullable, property"
        string op_comp_id FK "nullable, operation"
        string role "base_set | structure | axiom"
    }

    ENTITY_DEPENDENCY {
        string source_id FK,PK "who references"
        string target_id FK,PK "what is referenced"
    }

    BOOK {
        string key PK "zorich-1"
        string author "Зорич В.А."
        string title "Математический анализ т. I"
        string edition "10-е изд."
        int year "2012"
        string file "path in Books/"
    }

    FORMULATION {
        int id PK "autoincrement"
        string entity_id FK
        string entity_type "object | property | axiom | theorem"
        string source_book FK "book.key"
        string source_ref "p. 42 (scan page)"
        text content "verbatim LaTeX"
    }

    %% --- Core Relationships ---

    OBJECT ||--o{ OBJECT_PROPERTY : ""
    PROPERTY ||--o{ OBJECT_PROPERTY : ""

    OPERATION }o--|| OBJECT : "codomain"
    OPERATION ||--|{ OPERATION_ARGUMENT : "has_args"
    OPERATION_ARGUMENT }o--|| OBJECT : "typed_by"

    THEOREM }o--o{ OBJECT : "about"
    THEOREM }o--o{ PROPERTY : "uses"
    THEOREM }o--o{ OPERATION : "uses"
    THEOREM }o--o{ AXIOM : "grounded_in"
    THEOREM ||--o{ THEOREM : "parent_of"

    %% --- Edge Case Structures ---

    THEOREM ||--o{ THEOREM_DEPENDENCY : "depends_on"
    OBJECT ||--o{ EQUIVALENCE : "equivalent_to"
    OBJECT ||--o{ OBJECT_COMPOSITION : "composed_of"

    %% --- Cross-References (\entityref) ---

    ENTITY_DEPENDENCY }o--|| AXIOM : "depends_on"
    ENTITY_DEPENDENCY }o--|| OBJECT : "depends_on"
    ENTITY_DEPENDENCY }o--|| PROPERTY : "depends_on"
    ENTITY_DEPENDENCY }o--|| OPERATION : "depends_on"
    ENTITY_DEPENDENCY }o--|| THEOREM : "depends_on"

    %% --- Multi-Source Formulations ---

    BOOK ||--o{ FORMULATION : "provides"
    FORMULATION }o--|| OBJECT : "formulates"
    FORMULATION }o--|| PROPERTY : "formulates"
    FORMULATION }o--|| AXIOM : "formulates"
    FORMULATION }o--|| THEOREM : "formulates"
```

### 1.2 SQL Physical Schema (SQLite)

```sql
-- Dialect: SQLite 3.38+
-- PRAGMA foreign_keys = ON;
-- === CORE ENTITIES ===

CREATE TABLE axiom (
    id       TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    system   TEXT NOT NULL,       -- 'ZFC' | 'FOL' | 'Tool'
    statement TEXT NOT NULL,      -- LaTeX (canonical)
    file_path TEXT NOT NULL
);

CREATE TABLE object (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    aliases          TEXT,         -- JSON array
    module           TEXT NOT NULL,
    formal_definition TEXT NOT NULL, -- LaTeX (canonical)
    intuition        TEXT,
    file_path        TEXT NOT NULL
);

CREATE TABLE property (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    aliases          TEXT,
    module           TEXT NOT NULL,
    formal_definition TEXT NOT NULL,
    equivalent_forms TEXT,
    file_path        TEXT NOT NULL
);

CREATE TABLE operation (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    aliases          TEXT,
    module           TEXT NOT NULL,
    arity            INTEGER NOT NULL DEFAULT 1,
    formal_definition TEXT NOT NULL,
    codomain_id      TEXT REFERENCES object(id),
    file_path        TEXT NOT NULL
);

CREATE TABLE theorem (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    subtype           TEXT NOT NULL CHECK (subtype IN ('theorem','lemma')),
    parent_theorem_id TEXT REFERENCES theorem(id),
    module            TEXT NOT NULL,
    statement         TEXT NOT NULL,
    proof             TEXT NOT NULL,
    strategy          TEXT,
    file_path         TEXT NOT NULL,
    CHECK (
        (subtype = 'lemma' AND parent_theorem_id IS NOT NULL) OR
        (subtype = 'theorem' AND parent_theorem_id IS NULL)
    )
);

-- === JUNCTION / RELATIONSHIP TABLES ===

CREATE TABLE object_property (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id   TEXT NOT NULL REFERENCES object(id),
    property_id TEXT NOT NULL REFERENCES property(id),
    context     TEXT,
    context_ref TEXT REFERENCES object(id)
);

CREATE TABLE operation_argument (
    operation_id TEXT REFERENCES operation(id),
    position     INTEGER NOT NULL,
    object_id    TEXT REFERENCES object(id),
    role         TEXT DEFAULT 'operand',
    PRIMARY KEY (operation_id, position)
);

CREATE TABLE theorem_object (
    theorem_id TEXT REFERENCES theorem(id),
    object_id  TEXT REFERENCES object(id),
    PRIMARY KEY (theorem_id, object_id)
);

CREATE TABLE theorem_property (
    theorem_id  TEXT REFERENCES theorem(id),
    property_id TEXT REFERENCES property(id),
    PRIMARY KEY (theorem_id, property_id)
);

CREATE TABLE theorem_operation (
    theorem_id   TEXT REFERENCES theorem(id),
    operation_id TEXT REFERENCES operation(id),
    PRIMARY KEY (theorem_id, operation_id)
);

CREATE TABLE theorem_axiom (
    theorem_id TEXT REFERENCES theorem(id),
    axiom_id   TEXT REFERENCES axiom(id),
    PRIMARY KEY (theorem_id, axiom_id)
);

CREATE TABLE theorem_dependency (
    theorem_id  TEXT REFERENCES theorem(id),
    used_thm_id TEXT REFERENCES theorem(id),
    proof_step  TEXT,
    PRIMARY KEY (theorem_id, used_thm_id)
);

CREATE TABLE equivalence (
    entity_a_id TEXT NOT NULL,
    entity_b_id TEXT NOT NULL,
    proof_id    TEXT REFERENCES theorem(id),
    PRIMARY KEY (entity_a_id, entity_b_id),
    CHECK (entity_a_id < entity_b_id)
);

CREATE TABLE object_composition (
    container_id   TEXT NOT NULL REFERENCES object(id),
    obj_comp_id    TEXT REFERENCES object(id),
    prop_comp_id   TEXT REFERENCES property(id),
    op_comp_id     TEXT REFERENCES operation(id),
    role           TEXT NOT NULL,
    CHECK (
        (obj_comp_id  IS NOT NULL) +
        (prop_comp_id IS NOT NULL) +
        (op_comp_id   IS NOT NULL) = 1
    )
);

-- === CROSS-REFERENCES (from \entityref in content/) ===

CREATE TABLE entity_dependency (
    source_id  TEXT NOT NULL,  -- entity that references another
    target_id  TEXT NOT NULL,  -- entity being referenced
    PRIMARY KEY (source_id, target_id)
);

-- === MULTI-SOURCE FORMULATIONS ===

CREATE TABLE book (
    key     TEXT PRIMARY KEY,
    author  TEXT NOT NULL,
    title   TEXT NOT NULL,
    edition TEXT,
    year    INTEGER,
    file    TEXT
);

CREATE TABLE formulation (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN
                    ('axiom','object','property','operation','theorem')),
    source_book TEXT NOT NULL REFERENCES book(key),
    source_ref  TEXT NOT NULL, -- format: 'p. PAGE_NUM' to prevent ambiguity
    content     TEXT NOT NULL,
    UNIQUE(entity_id, source_book)
);

CREATE TABLE formulation_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    source_book TEXT NOT NULL,
    source_ref TEXT
);

CREATE TABLE formulation_raw_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT NOT NULL,
    query TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    cluster_id TEXT
);

-- FTS index
CREATE VIRTUAL TABLE entity_fts USING fts5(
    entity_id, entity_type, name, content
);
```

### 1.3 Reading the Diagram

| Relationship | Cardinality | Rationale |
|---|---|---|
| `OBJECT ↔ PROPERTY` | **M:N + context** | `prop-bounded` применимо к разным объектам; `context` указывает условия |
| `OPERATION → OPERATION_ARGUMENT` | 1:N | Поддержка N-арных операций |
| `OPERATION → OBJECT (codomain)` | N:1 | Каждая операция имеет один тип результата |
| `THEOREM ↔ OBJECT/PROPERTY/OPERATION/AXIOM` | M:N | Через junction tables |
| `THEOREM → THEOREM (parent_of)` | 1:N self | Лемма принадлежит ровно одной теореме |
| `THEOREM → THEOREM (dependency)` | **M:N (DAG)** | Логические зависимости |
| `OBJECT ↔ OBJECT (equivalence)` | M:N sym. | Эквивалентные определения, с proof_id |
| `OBJECT → OBJECT (composition)` | 1:N | Объект-контейнер |
| `ENTITY → ENTITY (entity_dependency)` | **M:N (DAG)** | Перекрёстные ссылки `\entityref` в `content/` |
| `BOOK → FORMULATION` | 1:N | Книга предоставляет N формулировок |
| `ENTITY ← FORMULATION` | 1:N | Сущность может иметь N формулировок из разных книг |

---

## 2. Three-Layer Content Architecture

### 2.1 Overview

```
┌────────────────────────────────────────┐
│  Layer 1: content/                     │  Канонические сущности
│  Одна формула на сущность              │  (source of truth for WHAT)
│  \entityref{id}{text} — гиперссылки    │  → entity_dependency таблица
├────────────────────────────────────────┤
│  Layer 2: sources/                     │  Транскрипции учебников
│  .tex по разделам                      │  (source of truth for HOW)
├────────────────────────────────────────┤
│  Layer 3: \label{entity:ID}            │  Линковка
│  внутри source .tex файлов             │  (maps Layer 2 → Layer 1)
└────────────────────────────────────────┘

Pipeline:  content/ + sources/  →  parser.py  →  seed_from_content.py  →  SQLite  →  web/
```

### 2.2 Layer 1: `content/` — Canonical Entities

```
content/
├── mathesis.sty                        ← shared preamble (\entityref)
├── master.tex                          ← master doc → PDF with hyperlinks
│
├── foundations/
│   ├── Modus Ponens [axm-fol-modus-ponens].tex
│   ├── Universal Instantiation [axm-fol-univ-inst].tex
│   ├── Axiom of Extensionality [axm-zfc-extensionality].tex
│   ├── Axiom of Choice [axm-zfc-choice].tex
│   ├── Completeness Axiom [axm-zfc-completeness].tex
│   └── Well-Ordering Principle [tool-well-ordering].tex
│
├── objects/
│   ├── Set [obj-set].tex
│   ├── Empty Set [obj-empty-set].tex
│   ├── Function [obj-function].tex
│   ├── Sequence [obj-sequence].tex
│   ├── Subsequence [obj-subsequence].tex
│   ├── Natural Numbers [obj-natural-numbers].tex
│   ├── Real Numbers [obj-real-numbers].tex
│   ├── Group [obj-group].tex
│   ├── Ring [obj-ring].tex
│   └── Field [obj-field].tex
│
├── properties/
│   ├── Bounded [prop-bounded].tex
│   ├── Continuity [prop-continuity].tex
│   ├── Convergent [prop-convergent].tex
│   ├── Commutativity [prop-commutative].tex
│   └── Completeness [prop-complete].tex
│
├── operations/
│   ├── Limit of Sequence [op-limit-seq].tex
│   ├── Derivative [op-derivative].tex
│   ├── Integral [op-integral].tex
│   ├── Set Union [op-union].tex
│   └── Absolute Value [op-absolute-value].tex
│
└── theorems/
    ├── Bolzano-Weierstrass [thm-bolzano-weierstrass].tex
    ├── BW Bisection [lemma-bw-bisection].tex
    ├── BW Subsequence Extraction [lemma-bw-subsequence].tex
    ├── Nested Intervals [thm-nested-intervals].tex
    ├── Intermediate Value [thm-intermediate-value].tex
    └── Cantor Diagonal [thm-cantor-diagonal].tex
```

> [!IMPORTANT]
> **Pure Math Absolute Rule.** Канонические файлы в `content/` НЕ ДОЛЖНЫ содержать
> текста на естественном языке (русском, английском и т.д.). Внутри
> `\begin{object}` / `\begin{axiom}` / `\begin{theorem}` допускаются **исключительно**
> математические символы в LaTeX math mode. Единственное исключение — содержимое
> `\text{}` для стандартных терминов (e.g. `\text{sgn}`). Все словесные пояснения
> формируются **только** на этапе генерации ответа инструментом `pipeline/generate_answer.py`
> (см. Раздел 9).

> [!IMPORTANT]
> **Recursive Exhaustion Rule.** Каждый символ, предикат или `\entityref`, используемый
> в каноническом определении, **обязан** иметь собственный `.tex` файл в `content/`.
> При создании новой сущности агент обязан выполнить **обход в ширину (BFS)** по всем
> зависимостям и создать канонические записи для каждой обнаруженной сущности,
> вплоть до аксиом ZFC/FOL из `content/foundations/`, которые не требуют доказательств.
> BFS останавливается, когда зависимость уже существует как файл `.tex` в `content/`
> или является аксиомой.

> [!CAUTION]
> **Full `\entityref` Coverage Rule.** Каждый символ в формуле, имеющий самостоятельное
> математическое определение, **ОБЯЗАН** быть обёрнут в `\entityref{entity-id}{символ}`.
> BFS-алгоритм обнаруживает зависимости **исключительно** через `\entityref`. Необёрнутый
> символ = невидимая зависимость = разрыв в цепочке до аксиом.
>
> **Оборачивать (семантические сущности):**
> - Операторы: `\sup` → `\entityref{op-supremum}{\sup}`, `\inf`, `\lim`, `\sum`, `\int`
> - Объекты: `f` → `\entityref{obj-function}{f}`, `[a,b]` → `\entityref{obj-closed-interval}{[a,b]}`
> - Свойства: «ограниченная f» → `\entityref{prop-bounded}{f}`
>
> **НЕ оборачивать (терминалы):**
> - Логические примитивы FOL: `\forall`, `\exists`, `\Rightarrow`, `\Leftrightarrow`, `\land`, `\lor`, `\lnot`
> - Примитивы ZFC: `\in`, `\emptyset`, `\subset` (определены в `content/foundations/`)
> - Локальные переменные: `x`, `n`, `i`, `a`, `b`
> - Нотационные сокращения: `\Delta x_i`, индексы, скобки
> - Числовые литералы: `0`, `1`, `\infty`
> - Равенство и неравенства: `=`, `<`, `>`, `\leq`, `\geq`

### 2.3 Cross-References: `\entityref`

Файлы в `content/` ссылаются друг на друга через `\entityref{id}{text}`.

**Пакет** `content/mathesis.sty`:

```tex
\ProvidesPackage{mathesis}
\RequirePackage{hyperref}
\RequirePackage{amsmath, amssymb, mathtools}
\newcommand{\entityref}[2]{\hyperref[entity:#1]{#2}}
```

**Мастер-документ** `content/master.tex` собирает все файлы → один PDF с рабочими гиперссылками:

```tex
\documentclass[a4paper]{article}
\usepackage{mathesis}
\begin{document}
\input{foundations/Axiom of Extensionality [axm-zfc-extensionality]}
\input{objects/Set [obj-set]}
% ...
\end{document}
```

**Пример использования** в файле сущности:

```tex
% entity-id: obj-function
% entity-type: object
\section{definition}
\label{entity:obj-function}

\mForall{\entityref{obj-set}{X},\; \entityref{obj-set}{Y}}
\text{\textit{функция}} \; f \colon X \to Y
\mDefIff
f \subset \entityref{obj-cartesian-product}{X \times Y} \;\land\;
\forall\, x \in X \;\; \exists!\, y \in Y \colon\quad (x, y) \in f
```

**Парсер** извлекает зависимости:

```python
import re
def extract_dependencies(content: str) -> list[str]:
    return list(set(re.findall(r'\\entityref\{([^}]+)\}', content)))
```

Результат: `['obj-set', 'obj-cartesian-product']` → записывается в `entity_dependency`.

**Обратные ссылки** (`used_by`) вычисляются API-запросом:
```sql
SELECT source_id FROM entity_dependency WHERE target_id = ?;
```

### 2.4 Layer 2: `sources/` — Textbook Transcriptions

```
sources/
├── _registry.yaml
├── zorich-1/
│   ├── _meta.yaml
│   ├── ch03s01-sequences.tex
│   └── ...
└── rudin/
    ├── _meta.yaml
    └── ch03-sequences.tex
```

Определения/теоремы внутри source `.tex` помечены `\label{entity:ID}`:

```tex
\begin{definition}
\label{entity:prop-convergent}
Число $A$ называется пределом последовательности $\{x_n\}$, если
для любого $\varepsilon > 0$ найдётся номер $N$...
\end{definition}
```

> [!IMPORTANT]
> `\entityref` используется **только** в `content/` (канонические определения).
> Файлы `sources/` содержат `\label{entity:ID}` для линковки с Layer 1, но **не** используют `\entityref`.

---

## 3. Semantics: Lemma (Model A)

**Lemma** — вспомогательное утверждение, принадлежащее ровно одной родительской теореме.

### Rules

1. `subtype: lemma` ⟹ `parent_theorem_id` **NOT NULL**
2. Лемма не может существовать без родительской теоремы
3. Если лемма оказывается полезной в другом контексте — она **повышается** до `subtype: theorem`
4. Связь: `THEOREM ||--o{ THEOREM : "parent_of"` — одна теорема -> 0..N лемм

### File Convention

Лемма именуется с префиксом родительской теоремы:

```
BW Bisection [lemma-bw-bisection].tex
BW Subsequence Extraction [lemma-bw-subseq].tex
```

---

## 4. File Naming Convention

### 4.1 Format

```
Human Name [id].tex
```

### 4.2 Rules

1. **Human Name** — English, Title Case, spaces allowed
2. **`[id]`** — lowercase, hyphenated, prefixed by type: `obj-`, `prop-`, `op-`, `thm-`, `lemma-`, `axm-`
3. No nested folders inside entity directories (flat)

### 4.3 Parsing Rule

```python
import re

def parse_filename(filename: str):
    match = re.match(r'^(.+?) \[([a-z\-]+)\]\.tex$', filename)
    if match:
        return {"name": match.group(1), "id": match.group(2)}
```

---

## 5. Book Naming Convention (Standardized)

**Format:** `Author - Title - (LANG) - [Year].pdf`

- **Author:** Фамилия И.О. (на латинице).
- **Title:** Название книги (на английском).
- **LANG:** `(EN)` или `(RU)`.
- **Year:** `[2021]` или `[10th ed]`.

**Examples:**
- `Zorich V.A. - Mathematical Analysis I - (RU) - [2012].pdf`
- `Rudin W. - Principles of Mathematical Analysis - (EN) - [1976].pdf`

---

## 6. Canonical Notation Rules

All `\section{definition}` / `\section{statement}` in `content/` use these rules:

### Quantifiers & Logic

| Rule | Canonical Macro (`mathesis.sty`) | Avoid |
|---|---|---|
| Quantifiers | `\mForall{x}`, `\mExists{x}` | `\forall x`, `\exists x` |
| Separator | `\;\;` (or built-in to macro) | comma, colon |
| Colon before condition | `\colon` + `\quad` | plain `:` |
| Implication | `\mImplies` | `\Rightarrow`, `\implies` |
| Iff | `\mIff` | `\Longleftrightarrow`, `\iff` |
| Def-equal | `\mDefIff` | `:=`, `\stackrel{\text{def}}{\Longleftrightarrow}` |

### Sets & Numbers

| Rule | Canonical Macro (`mathesis.sty`) | Avoid |
|---|---|---|
| Number sets | `\mReal`, `\mNatural`, `\mInteger`, `\mRational` | `\mathbb{R}`, `\mathbb{N}` |
| Empty set | `\mEmpty` | `\varnothing`, `\emptyset` |
| Set builder | `\mSet{x \in X \mid P(x)}` | `\{x : P(x)\}` |

### Variables

| Rule | Canonical |
|---|---|
| Sequence members | $x_n$, $a_n$ (lowercase Latin) |
| Index | $n, m, k$ (for ℕ) |
| Epsilon | `\varepsilon` (never `\epsilon`) |
| Limit value | $A$ (uppercase) |

### Layout

| Rule | Canonical |
|---|---|
| One concept per definition | no conjunctions |
| Display math only | no inline in definitions |
| **No natural language (absolute)** | **Запрещён любой текст на естественном языке внутри `content/`. `\text{}` допускается только для стандартных математических терминов (e.g. `\text{sgn}`, `\text{const}`). Описания на русском/английском языке генерируются исключительно в `result.tex` инструментом `pipeline/generate_answer.py`.** |
| Proof end | `\mQED` |

---

## 7. API Architecture

### 7.1 Layer Diagram

```
┌────────────────────────────────────────────────────┐
│              Transport layers                       │
│  ┌────────┐  ┌──────────┐  ┌────────────────────┐  │
│  │  Web   │  │   CLI    │  │  Desktop (future)  │  │
│  │ FastAPI│  │ argparse │  │  Qt / Tauri        │  │
│  └───┬────┘  └────┬─────┘  └────────┬───────────┘  │
│      │            │                 │               │
│      └────────────┴─────────────────┘               │
│                     │                               │
├─────────────────────┼───────────────────────────────┤
│                     ▼                               │
│           MathesisDB (core.py)                      │
│           ┌─────────────────┐                       │
│           │  Facade class   │                       │
│           └─────┬───────────┘                       │
│        ┌────────┼────────┬──────────┐               │
│        ▼        ▼        ▼          ▼               │
│     db.py   queries.py  validator.py  parser.py     │
│     (DDL)   (read)      (check)       (tex→model)  │
│        │        │        │             │            │
│        └────────┴────────┴─────────────┘            │
│                     │                               │
│              SQLite (mathesis_index.db)              │
└────────────────────────────────────────────────────┘
```

### 7.2 MathesisDB Public API

```python
class MathesisDB:
    # --- Lifecycle ---
    def connect() -> None
    def close() -> None
    def init_db() -> None
    def reset_db() -> None

    # --- CRUD: Entities ---
    def get_axiom(id) -> Axiom
    def get_object(id) -> Object
    def get_property(id) -> Property
    def get_operation(id) -> Operation
    def get_theorem(id) -> Theorem
    def list_axioms() -> list[Axiom]
    def list_objects(module?) -> list[Object]
    def list_properties(module?) -> list[Property]
    def list_operations(module?) -> list[Operation]
    def list_theorems(module?, subtype?) -> list[Theorem]
    def create_axiom(Axiom) -> Axiom
    def create_object(Object) -> Object
    def create_property(Property) -> Property
    def create_operation(Operation) -> Operation
    def create_theorem(Theorem) -> Theorem

    # --- Relationships ---
    def get_object_properties(object_id) -> list[ObjectProperty]
    def get_operation_arguments(op_id) -> list[OperationArgument]
    def get_lemmas(theorem_id) -> list[Theorem]
    def get_dependencies(theorem_id) -> list[Theorem]

    # --- Cross-References (\entityref) ---
    def get_entity_dependencies(entity_id) -> list[str]   # what this entity references
    def get_entity_dependents(entity_id) -> list[str]     # who references this entity

    # --- Backlinks ---
    def get_used_by(entity_id) -> UsedByResult

    # --- Graph ---
    def trace_to_axioms(theorem_id) -> list[TraceNode]
    def get_full_dag() -> list[TheoremDependency]

    # --- Equivalences & Composition ---
    def get_equivalents(object_id) -> list[Equivalence]
    def get_components(object_id) -> list[ObjectComposition]
    def get_containers(component_id) -> list[Object]

    # --- Formulations (NEW) ---
    def get_formulations(entity_id) -> list[Formulation]
    def list_books() -> list[Book]

    # --- Search ---
    def search(query, entity_type?) -> list[SearchResult]

    # --- Catalog ---
    def list_modules() -> list[str]
    def list_by_module(module) -> dict

    # --- Validation ---
    def validate() -> ValidationReport

    # --- Junction helpers ---
    def link_theorem_object(theorem_id, object_id) -> None
    def link_theorem_property(theorem_id, property_id) -> None
    def link_theorem_operation(theorem_id, operation_id) -> None
    def link_theorem_axiom(theorem_id, axiom_id) -> None
    def link_theorem_dependency(theorem_id, used_thm_id, proof_step?) -> None
    def link_object_property(object_id, property_id, context?, context_ref?) -> None
    def add_operation_argument(OperationArgument) -> None
    def add_equivalence(a_id, b_id, proof_id?) -> None
    def add_composition(ObjectComposition) -> None
    def add_formulation(Formulation) -> None       # NEW
    def register_book(Book) -> None                # NEW
```

### 7.3 Web Routes (FastAPI)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Homepage — entity counts, module list |
| GET | `/axioms/{id}` | Axiom detail + formulations |
| GET | `/objects/{id}` | Object detail + properties + formulations |
| GET | `/properties/{id}` | Property detail + formulations |
| GET | `/operations/{id}` | Operation detail + arguments + formulations |
| GET | `/theorems/{id}` | Theorem + proof + lemmas + DAG trace + formulations |
| GET | `/modules/{module}` | All entities in module |
| GET | `/search?q=...` | FTS search |
| GET | `/graph` | Full theorem DAG visualization |
| GET | `/books` | List of source books |
| GET | `/books/{key}` | Book detail + all formulations |

---

## 8. N-ary Operation Example

| Operation | Arity | Arg 0 | Arg 1 | Codomain |
|---|---|---|---|---|
| `op-limit-seq` (Предел) | 1 | `obj-sequence` | — | `obj-real-numbers` |
| `op-addition` (Сложение) | 2 | `obj-real-numbers` | `obj-real-numbers` | `obj-real-numbers` |
| `op-composition` (Композиция) | 2 | `obj-function` | `obj-function` | `obj-function` |
| `op-derivative` (Производная) | 1 | `obj-function` | — | `obj-function` |

---

## 9. Dynamic Compiler (Генератор ответов)

Канонические файлы в `content/` хранят **только** строгую математику (см. Pure Math Absolute Rule в Разделе 2.2). Для формирования человекочитаемого ответа используется отдельный инструмент.

### 9.1 Инструмент: `pipeline/generate_answer.py`

Скрипт выполняет следующий цикл:

1. **Сбор формул.** Читает запрошенные `.tex` файлы из `content/`, извлекает чистую математику из `\[ ... \]` и метаданные (`defined-in`, `entity-type`).
2. **Линковка с учебниками.** По метаданным `defined-in` определяет источник из `sources/_registry.yaml` и добавляет в вывод ссылку на учебник и страницу.
3. **Синтез естественного языка.** Транслирует строгую математическую запись в человекочитаемый текст (русский язык + формулы), используя LLM или шаблонизированный подход.
4. **Формирование `result.tex`.** Генерирует итоговый файл в формате `\documentclass{report}` со структурой `\chapter` / `\section`.
5. **Компиляция.** Вызывает `pdflatex` для сборки `result.pdf`.

### 9.2 Формат вывода

Формулировки в `result.tex` **допускают и приветствуют** использование естественного языка вперемешку с математическими формулами. Это единственное место в системе, где математика и слова объединяются.

```tex
\section{Окрестность точки}
\textbf{Источник:} Зорич В.А., Том I, стр. 42
\[ U_\varepsilon(x_0) = \mSet{x \mIn \mReal \mid |x - x_0| < \varepsilon} \]
$\varepsilon$-окрестностью точки $x_0$ называется множество всех вещественных чисел,
удаленных от $x_0$ на расстояние строго меньше $\varepsilon$.
```

---

## 10. Ensemble Extraction & Synthesis Pipeline

Начиная с версии 2.0 конвейер переведен на ансамблевый метод агрегации данных из нескольких источников для достижения математической полноты.

### 10.1 Стадии конвейера
1. **Extraction (Агрегация)** (`pipeline/ensemble_extractor.py`)
   - Извлекает сырые определения из списка учебников (`sources/_registry.yaml`).
   - Использует механизм **Sliding Context Window** (глубина окна: от начала параграфа до самого определения), чтобы не упустить неявные ограничения (например, ограниченность функции).
   - Сохраняет результат во временную таблицу БД `formulation_raw_cache`.

2. **Alignment (Выравнивание)** (`pipeline/entity_aligner.py`)
   - Прогоняет извлеченные тексты через локальную модель эмбеддингов Ollama (`nomic-embed-text`).
   - Использует библиотеку **FAISS** (`IndexFlatIP`) для быстрой векторной кластеризации (косинусное сходство).
   - Назначает схожим определениям общий `cluster_id`.

3. **Synthesis (Синтез)** (`pipeline/canonical_synthesizer.py`)
   - Передает весь кластер (включая предшествующий контекст) в LLM.
   - LLM выявляет скрытые ограничения (implicit constraints) и синтезирует единый строгий канонический файл `.tex`, строго соблюдая *Pure Math Absolute Rule*.
   - Сохраняет файл в `content/` и удаляет временные записи из `formulation_raw_cache`.

4. **Linking (Связывание)** (`pipeline/link_content.py`)
   - Парсит мета-тег `% defined-in:` из `.tex` файлов и создает записи в `formulation_sources`, связывая каноническую сущность со списком использованных книг.
   - Автоматически прописывает ссылки `\entityref` с использованием `\ensuremath`, чтобы защитить математический контекст.

---

## 11. Terminal Primitives & `content/terminals/`

Терминальные примитивы (Terminal Primitives) — это фундаментальные математические символы (листья в DAG), которые определены либо аксиоматикой ZFC, либо логикой первого порядка (FOL).

### 11.1 Правила терминалов
- **ЗАПРЕЩЕНО** оборачивать их макросом `\entityref`.
- **НЕ генерируют** ребер в графе зависимостей `entity_dependency`.
- Жестко закодированы в `pipeline/terminals.py` (`\forall`, `\in`, `\land`, `\emptyset` и т.д.).

### 11.2 Директория `content/terminals/`
Для предоставления человекочитаемых описаний терминалов используется специальная директория `content/terminals/`.
- **Исключение из Pure Math Rule**: В файлах этой директории разрешено использование естественного языка (комментарии, метафоры, примеры).
- **Исключение из Lean Export**: Скрипт трансляции `export_to_lean.py` полностью игнорирует эту директорию, так как для Lean терминалы являются встроенными константами.

---

## 12. Late Binding & Abstract Parametric Macros

Архитектура использует паттерн "Позднее связывание" (Late Binding) для разрешения полиморфизма математических операций (например, норма вектора, абсолютное значение, супремум).

### 12.1 Механика макросов
Все абстрактные операции определены в `mathesis.sty` с опциональным аргументом для `entity-id`:

```latex
% #1 — optional entity-id (default = abstract interface id)
% #2 — mandatory operand
\newcommand{\mNorm}[2][op-norm-abstract]{\left\| #2 \right\|}
```

### 12.2 Разделение ответственности
1. **LLM-Экстрактор**: Генерирует только абстрактный вызов без квадратных скобок (Surface Syntax): `\mNorm{x}`.
2. **Lean Elaborator (Future)**: Анализирует типы из Strict Typing Block и выполняет Typeclass Resolution.
3. **Graph Mutator (Future)**: Возвращается к исходному `.tex` файлу и инжектирует вычисленный конкретный инстанс в опциональный аргумент: `\mNorm[op-norm-euclidean]{x}`.

---

## 13. Strict Typing Block Convention

Чтобы обеспечить корректный вывод типов в Lean 4 и работу механизма Late Binding, каждая формулировка должна содержать жесткий блок объявления типов (Strict Typing Block).

### 13.1 Правила типизации
1. Каждое определение/теорема **обязано** начинаться с блока объявления типов.
2. **Любая переменная**, используемая в `Definitional Body`, обязана быть объявлена через квантор с явным указанием её принадлежности к множеству или типу.

### 13.2 Шаблон
```latex
% ПРАВИЛЬНО (Strict Typing Block):
\mForall{f \colon \entityref{obj-closed-interval}{[a,b]} \mTo \entityref{obj-real-numbers}{\mReal}}
\mForall{\varepsilon > 0}
... (тело)

% НЕПРАВИЛЬНО:
\mAbs{f(x)} < \varepsilon  % Откуда взялись f, x, \varepsilon?
```
