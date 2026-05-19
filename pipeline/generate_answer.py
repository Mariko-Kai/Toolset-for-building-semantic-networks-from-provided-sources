import os
import re
from pathlib import Path
import subprocess
import shutil
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32' and getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
CONTENT_DIR = PROJECT_ROOT / "content"

def load_book_citations():
    citations = {
        "zorich": "Зорич В.А., Математический анализ, Том I",
        "apostol": "Apostol T.M., Mathematical Analysis",
        "spivak": "Spivak M., Calculus",
    }
    books_dir = PROJECT_ROOT / "Books"
    if not books_dir.exists():
        return citations

    try:
        for f in books_dir.iterdir():
            if f.is_file() and f.suffix.lower() == ".pdf":
                name = f.stem
                parts = name.split(" - ")
                if len(parts) >= 2:
                    author = parts[0].strip()
                    title = parts[1].strip()
                    citation_str = f"{author}, {title}"
                    
                    # Derive key: e.g. "Apostol, T.M." -> "apostol"
                    key_base = author.split(',')[0].strip().split()[0].lower()
                    if "zorich" in key_base:
                        citations[key_base] = "Зорич В.А., Математический анализ, Том I"
                    else:
                        citations[key_base] = citation_str
                    
                    # Also map full stem to support precise matches
                    citations[name.lower()] = citation_str
    except Exception as e:
        print(f"[Warning] Failed to load citations from Books directory: {e}. Falling back to default list.")
        
    return citations

BOOK_CITATIONS = load_book_citations()

NL_DESCRIPTIONS = {
    "op-riemann-integral": r"Определенным интегралом Римана от функции $f(x)$ на отрезке $[a,b]$ называется предел интегральных сумм $\sum f(\xi_i) \Delta x_i$ при стремлении максимальной длины частичного отрезка $\lambda(P)$ к нулю, независимо от выбора разбиения $P$ и промежуточных точек $\xi_i$.",
    "op-darboux-integral": r"Функция $f$ называется интегрируемой по Дарбу на отрезке $[a,b]$, если нижний интеграл Дарбу $\underline{I}$ равен верхнему интегралу Дарбу $\overline{I}$. Их общее значение называется интегралом Дарбу функции $f$ по отрезку $[a,b]$.",
    "op-lower-darboux-sum": r"Нижней суммой Дарбу называется сумма произведений инфимумов функции $f$ на каждом отрезке разбиения $[x_{i-1}, x_i]$ на длину этого отрезка $\Delta x_i$.",
    "op-upper-darboux-sum": r"Верхней суммой Дарбу называется сумма произведений супремумов функции $f$ на каждом отрезке разбиения $[x_{i-1}, x_i]$ на длину этого отрезка $\Delta x_i$.",
    "obj-partition": r"Разбиением отрезка $[a,b]$ называется конечное множество точек $P = \{x_0, x_1, \ldots, x_n\}$, таких что $a = x_0 < x_1 < \cdots < x_n = b$.",
    "obj-function": r"Функция $f$ из множества $X$ в множество $Y$ — это правило (или бинарное отношение), по которому каждому элементу $x \in X$ ставится в соответствие ровно один элемент $y \in Y$. Формально, это подмножество декартова произведения $X \times Y$, обладающее свойством однозначности.",
    "obj-real-numbers": r"Множество вещественных чисел $\mathbb{R}$ — это непрерывная числовая прямая. Формально $\mathbb{R}$ задается как полное (непрерывное) архимедово упорядоченное поле. В нем можно складывать, умножать, сравнивать элементы, и в нем нет «дырок» (каждое ограниченное сверху подмножество имеет точную верхнюю грань).",
    "obj-set": r"Множество — базовое, неопределяемое напрямую понятие математики. Множество представляет собой совокупность объектов произвольной природы, называемых его элементами. Все свойства множеств строго выводятся из аксиом системы Цермело-Френкеля (ZFC).",
}

TEMPLATE = r"""\documentclass{report}
\usepackage{mathesis}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}

\begin{document}

%(content)s

\end{document}
"""

def parse_canonical(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    
    source_match = re.search(r'% defined-in: (.*)', text)
    source = source_match.group(1).strip() if source_match else "Unknown"
    
    id_match = re.search(r'% entity-id: (.*)', text)
    entity_id = id_match.group(1).strip() if id_match else "unknown"
    
    type_match = re.search(r'% entity-type: (.*)', text)
    entity_type = type_match.group(1).strip() if type_match else "unknown"

    module_match = re.search(r'% module: (.*)', text)
    module = module_match.group(1).strip() if module_match else ""
    
    section_match = re.search(r'\\section\{(.*?)\}', text)
    title = section_match.group(1).strip() if section_match else entity_id
    
    formulas = re.findall(r'\\\[(.*?)\\\]', text, re.DOTALL)
    
    deps = list(set(re.findall(r'\\entityref\{([^{}]+)\}', text)))
    
    # Extract abstract macro dependencies
    macro_deps = {
        r'\mNorm': 'op-norm-abstract',
        r'\mAbs': 'op-abs-abstract',
        r'\mInner': 'op-inner-product-abstract',
        r'\mDist': 'op-dist-abstract',
        r'\mSup': 'op-supremum',
        r'\mInf': 'op-infimum',
        r'\mDeriv': 'op-derivative',
        r'\mIntegral': 'op-integral',
    }
    for macro, default_id in macro_deps.items():
        escaped = re.escape(macro)
        concrete = re.findall(rf'{escaped}\[([^\]]+)\]', text)
        if concrete:
            deps.extend(concrete)
        elif re.search(rf'{escaped}(?!\[)\{{', text):
            deps.append(default_id)
            
    deps = list(set(deps))
    
    # Extract the full body by removing metadata comments and redundant sections/labels
    body_lines = [line for line in text.split('\n') if not line.strip().startswith('%')]
    full_body = '\n'.join(body_lines).strip()
    full_body = re.sub(r'\\section\{.*?\}', '', full_body)
    full_body = re.sub(r'\\label\{entity:.*?\}', '', full_body)
    
    # Extract description before removing it
    nl_desc = ""
    # Match \textbf{Описание:} ... up to \begin{object/axiom/theorem/operation} or \end{document}
    # Use a non-greedy match that also captures \begin{itemize} blocks within the description
    desc_match = re.search(
        r'\\textbf\{Описание:\}\s*(.*?)(?=\\begin\{(?:object|axiom|theorem|operation|property)\}|\\textbf\{(?!Описание)\}|\\section|$)',
        full_body, flags=re.DOTALL
    )
    if desc_match:
        nl_desc = desc_match.group(1).strip()

    # Strip the Описание block from canonical output as it violates PURE MATH RULE
    full_body = re.sub(
        r'\\textbf\{Описание:\}\s*.*?(?=\\begin\{(?:object|axiom|theorem|operation|property)\}|\\textbf\{(?!Описание)\}|\\section|$)',
        '', full_body, flags=re.DOTALL
    )
    full_body = full_body.strip()
    
    return {
        "id": entity_id,
        "type": entity_type,
        "module": module,
        "title": title,
        "source": source,
        "formulas": formulas,
        "full_body": full_body,
        "nl_desc": nl_desc,
        "deps": deps,
        "path": filepath
    }

def find_entity_file(entity_id):
    pattern = f"[{entity_id}].tex"
    for dirpath, _, filenames in os.walk(CONTENT_DIR):
        for fn in filenames:
            if pattern in fn:
                return Path(dirpath) / fn
    return None

def bfs_collect(root_id, args=None):
    visited = []
    queue = [root_id]
    seen = set()
    
    while queue:
        eid = queue.pop(0)
        if eid in seen:
            continue
        seen.add(eid)
        
        fpath = find_entity_file(eid)
        if fpath is None:
            print(f"  [MISSING] {eid} — file not found. Triggering Pipeline v2 enrichment...")
            # Преобразуем ID в человеческий запрос (например, 'prop-partial-order' -> 'partial order')
            human_query = eid.split('-', 1)[1].replace('-', ' ') if '-' in eid else eid
            
            # Resolve module configs using passed args (or defaults)
            from pipeline.config import resolve_module_config
            from pipeline.ollama_wrapper import run_enrichment_pipeline
            
            extract_provider = extract_model = extract_api_key = None
            preview_provider = preview_model = preview_api_key = None
            synth_provider = synth_model = synth_api_key = None
            lean_provider = lean_model = lean_api_key = None
            cv_model = "glm-ocr"
            no_validate = False
            
            if args:
                extract_provider, extract_model, extract_api_key = resolve_module_config(
                    module="extract",
                    global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
                    module_provider=args.extract_provider, module_model=args.extract_model, module_api_key=args.extract_api_key,
                )
                preview_provider, preview_model, preview_api_key = resolve_module_config(
                    module="preview",
                    global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
                    module_provider=args.extract_preview_provider, module_model=args.extract_preview_model, module_api_key=args.extract_preview_api_key,
                )
                synth_provider, synth_model, synth_api_key = resolve_module_config(
                    module="synth",
                    global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
                    module_provider=args.synth_provider, module_model=args.synth_model, module_api_key=args.synth_api_key,
                )
                lean_provider = args.lean_provider
                lean_model = args.lean_model
                lean_api_key = args.lean_api_key
                cv_model = args.cv_model
                no_validate = args.no_validate

            try:
                success, generated, _ = run_enrichment_pipeline(
                    human_query,
                    extract_provider=extract_provider, extract_api_key=extract_api_key, extract_model=extract_model,
                    preview_provider=preview_provider, preview_api_key=preview_api_key, preview_model=preview_model,
                    synth_provider=synth_provider,     synth_api_key=synth_api_key,     synth_model=synth_model,
                    lean_provider=lean_provider,        lean_api_key=lean_api_key,        lean_model=lean_model,
                    cv_model=cv_model,
                    no_validate=no_validate,
                )
            except Exception as e:
                import traceback
                print(f"  [ERROR] Failed to run enrichment pipeline: {e}", flush=True)
                traceback.print_exc(file=sys.stdout)
                sys.exit(1)
            
            if success:
                fpath = find_entity_file(eid)
            if fpath is None:
                print(f"  [SKIP] {eid} — failed to generate or find.")
                continue

        
        data = parse_canonical(fpath)
        visited.append(data)
        print(f"  [BFS] {eid} -> deps: {data['deps']}")
        
        for dep in data['deps']:
            if dep not in seen:
                queue.append(dep)
    
    return visited

import argparse

def multi_root_bfs_collect(root_ids, args=None):
    """Runs BFS from multiple roots, merging graphs without duplication."""
    all_entities = []
    seen_ids = set()

    for root_id in root_ids:
        print(f"\n=== BFS от корня: {root_id} ===")
        branch = bfs_collect(root_id, args)
        for entity in branch:
            if entity["id"] not in seen_ids:
                seen_ids.add(entity["id"])
                all_entities.append(entity)

    return all_entities

def main():
    parser = argparse.ArgumentParser(description="Dynamic LaTeX Compiler via BFS (Multi-Root)")
    parser.add_argument('--root', type=str, default=None, help='Single root entity ID')
    parser.add_argument('--roots', type=str, default=None, help='Comma-separated root entity IDs')
    
    # Forwarded model configurations
    parser.add_argument("--cv-model", type=str, default="glm-ocr")
    parser.add_argument("--provider", type=str, default=None)
    parser.add_argument("--model",    type=str, default=None)
    parser.add_argument("--api-key",  type=str, default=None)

    parser.add_argument("--extract-provider", type=str, default=None)
    parser.add_argument("--extract-model",    type=str, default=None)
    parser.add_argument("--extract-api-key",  type=str, default=None)
    
    parser.add_argument("--extract-preview-provider", type=str, default=None)
    parser.add_argument("--extract-preview-model",    type=str, default=None)
    parser.add_argument("--extract-preview-api-key",  type=str, default=None)

    parser.add_argument("--synth-provider", type=str, default=None)
    parser.add_argument("--synth-model",    type=str, default=None)
    parser.add_argument("--synth-api-key",  type=str, default=None)

    parser.add_argument("--lean-provider", type=str, default=None)
    parser.add_argument("--lean-model",    type=str, default=None)
    parser.add_argument("--lean-api-key",  type=str, default=None)
    parser.add_argument("--no-validate", action='store_true')

    args = parser.parse_args()

    if args.roots:
        root_ids = [r.strip() for r in args.roots.split(',') if r.strip()]
    elif args.root:
        root_ids = [args.root]
    else:
        print("[-] Укажите --root или --roots")
        return

    # Resolve configurations for all modules
    from pipeline.config import resolve_module_config
    
    extract_provider, extract_model, extract_api_key = resolve_module_config(
        module="extract",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.extract_provider, module_model=args.extract_model, module_api_key=args.extract_api_key,
    )
    preview_provider, preview_model, preview_api_key = resolve_module_config(
        module="preview",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.extract_preview_provider, module_model=args.extract_preview_model, module_api_key=args.extract_preview_api_key,
    )
    synth_provider, synth_model, synth_api_key = resolve_module_config(
        module="synth",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.synth_provider, module_model=args.synth_model, module_api_key=args.synth_api_key,
    )

    print(f"=== DYNAMIC COMPILER: Сборка графа для {root_ids} (Multi-Root BFS) ===\n")

    entities = multi_root_bfs_collect(root_ids, args)

    print(f"\nCollected {len(entities)} unique entities. Running Lean validation and recursive enrichment...\n")

    # Recursive lean-validation loop: discover missing mathesis dependencies and trigger enrichment
    from pipeline.lean_validator import validate_entity
    from pipeline.ollama_wrapper import get_missing_deps_from_lean_error, run_enrichment_pipeline

    max_iters = 5
    iter_count = 0
    roots_changed = True
    while iter_count < max_iters and roots_changed:
        iter_count += 1
        roots_changed = False
        missing_terms = []
        for ent in entities:
            eid = ent["id"]
            lean_path = PROJECT_ROOT / "lean_validator" / "Validated" / f"{eid}.lean"
            if not lean_path.exists():
                continue
            lean_code = lean_path.read_text(encoding='utf-8')
            result = validate_entity(eid, lean_code)
            if result.get("status") != "success":
                # Log the Lean compile errors
                error_feedback = "\n".join([f"Line {e['line']}: {e['message']}" for e in result.get("errors", [])])
                from pipeline.export_to_lean import log_to_file
                log_to_file("lean_errors", error_feedback, entity_id=eid)
                
                missing = get_missing_deps_from_lean_error(result.get("errors", []))
                mathesis_deps = [d for d in missing if any(d.startswith(p) for p in ["obj-", "prop-", "op-", "thm-", "def-"]) ]
                for dep in mathesis_deps:
                    human = dep.split('-',1)[1].replace('-', ' ')
                    if human not in missing_terms:
                        missing_terms.append(human)
        if not missing_terms:
            break
        print(f"[Validation loop {iter_count}] Found missing dependencies to enrich: {missing_terms}")
        for term in missing_terms:
            ok, gen, _ = run_enrichment_pipeline(
                term,
                extract_provider=extract_provider, extract_api_key=extract_api_key, extract_model=extract_model,
                preview_provider=preview_provider, preview_api_key=preview_api_key, preview_model=preview_model,
                synth_provider=synth_provider,     synth_api_key=synth_api_key,     synth_model=synth_model,
                lean_provider=args.lean_provider,  lean_api_key=args.lean_api_key,  lean_model=args.lean_model,
                cv_model=args.cv_model,
                no_validate=args.no_validate,
            )
            if ok:
                roots_changed = True
        if roots_changed:
            # rebuild entities graph to include newly synthesized entities
            entities = multi_root_bfs_collect(root_ids, args)

    print(f"Validation/enrichment loop finished after {iter_count} iterations.")

    # Build and log the final graph structure for this query
    from pipeline.export_to_lean import log_to_file
    
    graph_lines = []
    graph_lines.append("=== FINAL GRAPH STRUCTURE ===")
    graph_lines.append(f"Query Roots: {root_ids}")
    graph_lines.append(f"Total Unique Entities: {len(entities)}\n")
    
    graph_lines.append("Nodes:")
    for ent in entities:
        graph_lines.append(f"  - {ent['id']} (Type: {ent['type']})")
        
    graph_lines.append("\nEdges (Dependencies):")
    for ent in entities:
        if ent.get('deps'):
            for dep in ent['deps']:
                graph_lines.append(f"  {ent['id']} -> {dep}")
        else:
            graph_lines.append(f"  {ent['id']} -> (No dependencies)")
            
    graph_content = "\n".join(graph_lines)
    
    # Save log to logs/graphs/ category using the combined roots as the entity_id
    combined_roots = "_".join(root_ids)
    log_to_file("graphs", graph_content, entity_id=combined_roots)

    content = ""
    for data in entities:
        book_key = data["source"].split(",")[0].strip()
        citation = BOOK_CITATIONS.get(book_key, data["source"])
        page_info = data["source"]
        
        nl = NL_DESCRIPTIONS.get(data["id"], "")
        if not nl:
            nl = data.get("nl_desc", "")
        
        block = f"\\section{{{data['title']}}}\\label{{entity:{data['id']}}}\n"
        block += f"\\textbf{{Тип:}} {data['type']}\\quad "
        if data.get('module'):
            block += f"\\textbf{{Модуль:}} {data['module']}\\quad "
        block += f"\\textbf{{Источник:}} {citation} ({page_info})\n\n"
        
        block += "\\textbf{Каноническая запись:}\n"
        block += f"\n{data.get('full_body', '')}\n\n"
        
        if nl:
            block += f"\n\\textbf{{Естественный язык:}}\n{nl}\n"
        
        block += "\n\\vspace{1em}\n\\hrule\n\\vspace{1em}\n\n"
        content += block
    
    result_tex = PROJECT_ROOT / "result.tex"
    with open(result_tex, "w", encoding="utf-8") as f:
        f.write(TEMPLATE % {"content": content})
    
    print(f"Generated {result_tex}")
    
    # Rebuild master.tex at the very end during result formation
    try:
        from pipeline.canonical_synthesizer import rebuild_master_tex
        rebuild_master_tex()
    except Exception as e:
        print(f"[WARN] Failed to rebuild master.tex: {e}")
    
    if not (PROJECT_ROOT / "mathesis.sty").exists():
        shutil.copy(CONTENT_DIR / "mathesis.sty", PROJECT_ROOT / "mathesis.sty")
    
    print("Compiling result.pdf (pass 1)...")
    os.chdir(PROJECT_ROOT)
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "result.tex"],
        capture_output=True, text=True
    )
    
    print("Compiling result.pdf (pass 2 for references)...")
    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "result.tex"],
        capture_output=True, text=True
    )
    
    if "Output written on result.pdf" in result.stdout:
        print("PDF compilation successful! -> result.pdf")
    else:
        print("PDF compilation issue. Last 500 chars of log:")
        print(result.stdout[-500:])

if __name__ == "__main__":
    main()
