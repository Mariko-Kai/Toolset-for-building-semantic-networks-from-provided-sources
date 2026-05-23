"""
Autonomous Pipeline Experiment — bypasses standard pipeline.
Phases: 1) Content inventory, 2) LLM synthesis, 3) Lean validation, 4) Stats export.
"""
import sqlite3, re, json, time, os, sys, io
from pathlib import Path
from collections import defaultdict

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
CONTENT_DIR = PROJECT_ROOT / "content"
DB_PATH = PROJECT_ROOT / "mathesis_index.db"
LEAN_DIR = PROJECT_ROOT / "lean_validator"
OUTPUT_DIR = PROJECT_ROOT / "scratch" / "experiment_output"

# ── Phase 1: Content Inventory ───────────────────────────────────────────────

def phase1_inventory():
    """Scan all .tex files in content/, extract metadata and dependency graph."""
    print("\n" + "="*60)
    print("PHASE 1: Content Inventory")
    print("="*60)
    
    entities = []
    dep_graph = defaultdict(list)
    
    for filepath in sorted(CONTENT_DIR.rglob("*.tex")):
        if filepath.name in ("master.tex", "TEMPLATE.tex", "mathesis.sty"):
            continue
        match = re.search(r'\[([^\]]+)\]\.tex$', filepath.name)
        if not match:
            continue
        
        entity_id = match.group(1)
        content = filepath.read_text(encoding='utf-8', errors='replace')
        
        # Parse metadata
        type_m = re.search(r'% entity-type:\s*(\w+)', content)
        src_m = re.search(r'% defined-in:\s*(.+)', content)
        entity_type = type_m.group(1) if type_m else "unknown"
        source = src_m.group(1).strip() if src_m else "unknown"
        
        # Detect type from directory if not in metadata
        if entity_type == "unknown":
            rel = filepath.relative_to(CONTENT_DIR).parts[0]
            type_map = {"foundations": "axiom", "objects": "object", "properties": "property",
                        "operations": "operation", "theorems": "theorem"}
            entity_type = type_map.get(rel, "unknown")
        
        # Extract dependencies
        deps = list(set(re.findall(r'\\entityref\{([^}]+)\}', content)))
        dep_graph[entity_id] = deps
        
        # Check for display math
        has_display_math = bool(re.search(r'\\\[.*?\\\]', content, re.DOTALL))
        # Check for natural language violations in formal blocks
        formal_blocks = re.findall(r'\\begin\{(object|theorem|property|operation|axiom)\}.*?\\end\{\1\}', content, re.DOTALL)
        
        entities.append({
            "id": entity_id, "type": entity_type, "source": source,
            "path": str(filepath.relative_to(PROJECT_ROOT)),
            "deps": deps, "dep_count": len(deps),
            "has_display_math": has_display_math,
            "size_bytes": filepath.stat().st_size,
            "formal_blocks": len(formal_blocks),
        })
        print(f"  [{entity_type:10s}] {entity_id} ({len(deps)} deps, {filepath.stat().st_size}B)")
    
    # Stats
    type_counts = defaultdict(int)
    for e in entities:
        type_counts[e["type"]] += 1
    
    print(f"\n  Total entities: {len(entities)}")
    for t, c in sorted(type_counts.items()):
        print(f"    {t}: {c}")
    
    # Find missing dependencies
    known_ids = {e["id"] for e in entities}
    missing = set()
    for eid, deps in dep_graph.items():
        for d in deps:
            if d not in known_ids:
                missing.add(d)
    print(f"  Missing dependencies (dangling \\entityref): {len(missing)}")
    if missing:
        for m in sorted(missing):
            print(f"    ⚠ {m}")
    
    return {"entities": entities, "dep_graph": dict(dep_graph),
            "type_counts": dict(type_counts), "missing_deps": sorted(missing)}


# ── Phase 2: LLM Synthesis ──────────────────────────────────────────────────

def phase2_synthesis(max_clusters=5, model="qwen3:8b"):
    """Synthesize entities from formulation_raw_cache using Ollama LLM."""
    print("\n" + "="*60)
    print(f"PHASE 2: LLM Synthesis (max {max_clusters} clusters, model={model})")
    print("="*60)
    
    from pipeline.canonical_synthesizer import synthesize_cluster
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT temp_cluster_id, GROUP_CONCAT(source_book, '|'), GROUP_CONCAT(raw_text, '\n---\n')
        FROM formulation_raw_cache
        WHERE temp_cluster_id IS NOT NULL
        GROUP BY temp_cluster_id
        ORDER BY LENGTH(GROUP_CONCAT(raw_text)) DESC
        LIMIT ?
    """, (max_clusters,))
    clusters = cursor.fetchall()
    conn.close()
    
    results = []
    for cid, sources_str, texts_str in clusters:
        sources = sources_str.split("|")
        texts = texts_str.split("\n---\n")
        
        print(f"\n  Cluster {cid}: {len(texts)} formulation(s) from {sources_str}")
        t0 = time.time()
        try:
            tex = synthesize_cluster(cid, texts, sources, model=model)
            elapsed = time.time() - t0
            
            # Parse result
            eid_m = re.search(r'^% entity-id:\s*(.+)$', tex or "", re.MULTILINE)
            etype_m = re.search(r'% entity-type:\s*(\w+)', tex or "")
            entity_id = eid_m.group(1).strip() if eid_m else "PARSE_FAIL"
            entity_type = etype_m.group(1).strip() if etype_m else "unknown"
            
            has_formal = bool(re.search(r'\\begin\{(object|theorem|property|operation)\}', tex or ""))
            has_math = bool(re.search(r'\\\[.*?\\\]', tex or "", re.DOTALL))
            
            result = {
                "cluster_id": cid, "entity_id": entity_id, "entity_type": entity_type,
                "sources": sources, "synthesis_time_s": round(elapsed, 1),
                "output_chars": len(tex or ""), "has_formal_block": has_formal,
                "has_display_math": has_math, "status": "ok" if has_formal else "degraded",
                "tex_content": tex,
            }
            print(f"  → {entity_id} ({entity_type}) in {elapsed:.1f}s, {len(tex or '')} chars")
        except Exception as e:
            elapsed = time.time() - t0
            result = {
                "cluster_id": cid, "entity_id": "ERROR", "entity_type": "error",
                "sources": sources, "synthesis_time_s": round(elapsed, 1),
                "output_chars": 0, "has_formal_block": False,
                "has_display_math": False, "status": f"error: {e}",
                "tex_content": None,
            }
            print(f"  → ERROR: {e}")
        
        results.append(result)
    
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n  Synthesis: {ok}/{len(results)} successful")
    return results


# ── Phase 3: Lean Translation & Validation ───────────────────────────────────

def phase3_lean_validation(entities_phase1, synthesis_phase2):
    """Translate entities to Lean 4, validate without Mathlib."""
    print("\n" + "="*60)
    print("PHASE 3: Lean Translation & Validation")
    print("="*60)
    
    from pipeline.export_to_lean import translate_to_lean_regex
    
    all_entities = []
    
    # Existing entities from content/
    for e in entities_phase1["entities"]:
        filepath = PROJECT_ROOT / e["path"]
        try:
            content = filepath.read_text(encoding='utf-8', errors='replace')
        except:
            content = ""
        all_entities.append((e["id"], e["type"], content, "existing"))
    
    # Newly synthesized entities
    for s in synthesis_phase2:
        if s.get("tex_content"):
            all_entities.append((s["entity_id"], s["entity_type"], s["tex_content"], "synthesized"))
    
    results = []
    lean_fragments = []
    
    for eid, etype, tex, origin in all_entities:
        # Strip proofs for translation
        tex_clean = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', tex, flags=re.DOTALL)
        lean_code = translate_to_lean_regex(eid, etype, tex_clean)
        
        if not lean_code:
            results.append({"entity_id": eid, "type": etype, "origin": origin,
                           "lean_status": "no_content", "lean_code": "", "errors": []})
            print(f"  [{origin:11s}] {eid}: no translatable content")
            continue
        
        # Syntax check: no LaTeX artifacts
        latex_artifacts = re.findall(r'\\\\(?:mathcal|mathbb|mForall|mExists|entityref|frac|colon|quad)', lean_code)
        has_balanced_parens = lean_code.count('(') == lean_code.count(')')
        has_type_decl = ':' in lean_code
        
        errors = []
        if latex_artifacts:
            errors.append(f"LaTeX artifacts: {latex_artifacts[:3]}")
        if not has_balanced_parens:
            errors.append("Unbalanced parentheses")
        if not has_type_decl:
            errors.append("Missing type declaration")
        
        status = "pass_syntax" if not errors else "fail_syntax"
        lean_fragments.append((eid, lean_code))
        
        results.append({"entity_id": eid, "type": etype, "origin": origin,
                        "lean_status": status, "lean_code": lean_code,
                        "lean_chars": len(lean_code), "errors": errors})
        print(f"  [{origin:11s}] {eid}: {status} ({len(lean_code)} chars)" +
              (f" ⚠ {errors}" if errors else ""))
    
    # Attempt real Lean 4 validation on clean fragments (without Mathlib)
    clean_fragments = [(eid, code) for eid, code in lean_fragments
                       if not any(r["errors"] for r in results if r["entity_id"] == eid)]
    
    lean_validated = 0
    lean_failed = 0
    lean_results_detail = []
    
    if clean_fragments:
        print(f"\n  Running Lean 4 type-check on {len(clean_fragments)} clean fragments...")
        temp_file = LEAN_DIR / "TempExperiment.lean"
        
        for eid, code in clean_fragments:
            # Write single entity
            temp_file.write_text(f"-- {eid}\n{code}\n", encoding='utf-8')
            try:
                import subprocess
                r = subprocess.run(
                    ["lake", "env", "lean", "--json", str(temp_file)],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(LEAN_DIR), encoding='utf-8', errors='replace'
                )
                if r.returncode == 0:
                    lean_validated += 1
                    lean_results_detail.append({"entity_id": eid, "lean_check": "pass"})
                    # Update result
                    for res in results:
                        if res["entity_id"] == eid:
                            res["lean_status"] = "lean_pass"
                    print(f"    ✓ {eid}: Lean OK")
                else:
                    lean_failed += 1
                    err_msgs = []
                    for line in r.stdout.strip().split('\n'):
                        try:
                            d = json.loads(line)
                            if d.get('severity') == 'error':
                                err_msgs.append(d.get('data', '')[:100])
                        except:
                            pass
                    lean_results_detail.append({"entity_id": eid, "lean_check": "fail", "errors": err_msgs[:2]})
                    for res in results:
                        if res["entity_id"] == eid:
                            res["lean_status"] = "lean_fail"
                            res["errors"] = err_msgs[:2]
                    print(f"    ✗ {eid}: {err_msgs[0][:80] if err_msgs else 'unknown error'}")
            except subprocess.TimeoutExpired:
                lean_results_detail.append({"entity_id": eid, "lean_check": "timeout"})
                print(f"    ⏱ {eid}: timeout")
            except Exception as ex:
                print(f"    ⚠ {eid}: {ex}")
        
        try:
            temp_file.unlink()
        except:
            pass
    
    stats = {
        "total": len(results),
        "no_content": sum(1 for r in results if r["lean_status"] == "no_content"),
        "pass_syntax": sum(1 for r in results if r["lean_status"] == "pass_syntax"),
        "fail_syntax": sum(1 for r in results if r["lean_status"] == "fail_syntax"),
        "lean_pass": lean_validated,
        "lean_fail": lean_failed,
    }
    print(f"\n  Lean results: {stats}")
    return {"results": results, "stats": stats, "lean_detail": lean_results_detail}


# ── Phase 4: Export Statistics ───────────────────────────────────────────────

def phase4_export(phase1, phase2, phase3):
    """Export all data as JSON and generate Markdown report."""
    print("\n" + "="*60)
    print("PHASE 4: Statistics Export")
    print("="*60)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Strip tex_content from synthesis results for JSON (keep it small)
    phase2_clean = []
    for r in phase2:
        rc = {k: v for k, v in r.items() if k != "tex_content"}
        phase2_clean.append(rc)
    
    # Strip lean_code from phase3 results
    phase3_clean = {"stats": phase3["stats"], "lean_detail": phase3["lean_detail"],
                    "results": [{k: v for k, v in r.items() if k != "lean_code"} for r in phase3["results"]]}
    
    # Save JSON
    data = {"phase1_inventory": phase1, "phase2_synthesis": phase2_clean,
            "phase3_lean": phase3_clean, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    
    json_path = OUTPUT_DIR / "experiment_results.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"  Saved: {json_path}")
    
    # Generate Markdown report
    md = generate_section4_markdown(phase1, phase2_clean, phase3_clean)
    md_path = OUTPUT_DIR / "section4_report.md"
    md_path.write_text(md, encoding='utf-8')
    print(f"  Saved: {md_path}")
    
    # Save CSV
    import csv
    csv_path = OUTPUT_DIR / "entities.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["entity_id", "type", "origin", "deps", "lean_status", "errors"])
        for r in phase3["results"]:
            e = next((e for e in phase1["entities"] if e["id"] == r["entity_id"]), None)
            dep_count = e["dep_count"] if e else 0
            w.writerow([r["entity_id"], r["type"], r["origin"], dep_count,
                        r["lean_status"], "; ".join(r.get("errors", []))])
    print(f"  Saved: {csv_path}")
    
    return {"json": str(json_path), "md": str(md_path), "csv": str(csv_path)}


def generate_section4_markdown(phase1, phase2, phase3):
    """Generate Section 4 markdown with tables."""
    tc = phase1["type_counts"]
    total = sum(tc.values())
    
    md = f"""# Раздел 4. Результаты эксперимента

## 4.1 Инвентаризация узлов семантической сети

| Тип сущности | Количество | Доля |
|---|---|---|
"""
    for t in ["axiom", "object", "property", "operation", "theorem", "unknown"]:
        c = tc.get(t, 0)
        if c > 0:
            md += f"| {t} | {c} | {c/total*100:.0f}% |\n"
    md += f"| **ИТОГО** | **{total}** | **100%** |\n"
    
    md += f"""
- Обнаружено незакрытых зависимостей (dangling `\\entityref`): **{len(phase1['missing_deps'])}**
"""
    if phase1["missing_deps"]:
        md += "- Отсутствующие сущности: " + ", ".join(f"`{d}`" for d in phase1["missing_deps"][:10]) + "\n"
    
    md += f"""
## 4.2 Синтез из кэша формулировок (LLM)

| # | Кластер | Источник | Время (с) | Статус | entity-id | Размер |
|---|---|---|---|---|---|---|
"""
    for i, r in enumerate(phase2, 1):
        src = ", ".join(r["sources"]) if isinstance(r["sources"], list) else r["sources"]
        md += f"| {i} | `{r['cluster_id'][:8]}` | {src} | {r['synthesis_time_s']} | {r['status']} | `{r['entity_id']}` | {r['output_chars']} |\n"
    
    ok = sum(1 for r in phase2 if r["status"] == "ok")
    md += f"\n**Результат:** {ok}/{len(phase2)} кластеров успешно синтезированы.\n"
    if phase2:
        avg_time = sum(r["synthesis_time_s"] for r in phase2) / len(phase2)
        md += f"Среднее время синтеза: **{avg_time:.1f}с** на кластер.\n"
    
    s = phase3["stats"]
    md += f"""
## 4.3 Lean-трансляция и валидация

| Метрика | Значение |
|---|---|
| Всего сущностей | {s['total']} |
| Нет транслируемого контента | {s['no_content']} |
| Прошли синтаксический анализ | {s['pass_syntax']} |
| Не прошли синтаксический анализ | {s['fail_syntax']} |
| Прошли Lean 4 type-check | {s['lean_pass']} |
| Не прошли Lean 4 type-check | {s['lean_fail']} |

"""
    # Detail table
    md += """### Детализация по сущностям

| entity-id | Тип | Источник | Lean-статус | Ошибки |
|---|---|---|---|---|
"""
    for r in phase3["results"]:
        errs = "; ".join(str(e)[:50] for e in r.get("errors", []))[:80]
        md += f"| `{r['entity_id']}` | {r['type']} | {r['origin']} | {r['lean_status']} | {errs} |\n"
    
    translated = s['total'] - s['no_content']
    if translated > 0:
        pass_rate = (s['lean_pass'] / translated * 100) if s['lean_pass'] else 0
        md += f"\n**Доля успешной Lean-валидации:** {s['lean_pass']}/{translated} ({pass_rate:.0f}%)\n"
    
    md += f"""
## 4.4 Сводная статистика

| Показатель | Значение |
|---|---|
| Узлов в `content/` (до эксперимента) | {total} |
| Синтезировано новых узлов | {ok} |
| Общее количество узлов (после) | {total + ok} |
| Валидация Lean (type-check) | {s['lean_pass']} из {translated} |
| Незакрытые зависимости | {len(phase1['missing_deps'])} |
"""
    return md


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Pipeline Experiment")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model for synthesis")
    parser.add_argument("--clusters", type=int, default=5, help="Number of clusters to synthesize")
    parser.add_argument("--skip-synthesis", action="store_true", help="Skip LLM synthesis phase")
    parser.add_argument("--skip-lean", action="store_true", help="Skip Lean validation phase")
    args = parser.parse_args()
    
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  MATHESIS PIPELINE EXPERIMENT — Autonomous Run          ║")
    print(f"║  Model: {args.model:20s}  Clusters: {args.clusters:3d}          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    
    t_start = time.time()
    
    # Phase 1
    phase1 = phase1_inventory()
    
    # Phase 2
    if args.skip_synthesis:
        phase2 = []
        print("\n  [SKIP] LLM synthesis skipped.")
    else:
        phase2 = phase2_synthesis(max_clusters=args.clusters, model=args.model)
    
    # Phase 3
    if args.skip_lean:
        phase3 = {"results": [], "stats": {"total": 0, "no_content": 0, "pass_syntax": 0,
                   "fail_syntax": 0, "lean_pass": 0, "lean_fail": 0}, "lean_detail": []}
        print("\n  [SKIP] Lean validation skipped.")
    else:
        phase3 = phase3_lean_validation(phase1, phase2)
    
    # Phase 4
    outputs = phase4_export(phase1, phase2, phase3)
    
    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"EXPERIMENT COMPLETE in {elapsed:.1f}s")
    print(f"  JSON: {outputs['json']}")
    print(f"  Report: {outputs['md']}")
    print(f"  CSV: {outputs['csv']}")


if __name__ == "__main__":
    main()
