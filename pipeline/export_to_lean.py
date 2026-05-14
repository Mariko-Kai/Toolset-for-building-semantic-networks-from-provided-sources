import sqlite3
import re
from pathlib import Path
from collections import defaultdict, deque

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "mathesis_index.db"
LEAN_DIR = PROJECT_ROOT / "lean_validator"
OUT_FILE = LEAN_DIR / "MathesisGraph.lean"

def get_graph():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT entity_id, type, path FROM entities")
    nodes = {row[0]: {"type": row[1], "path": PROJECT_ROOT / row[2]} for row in cursor.fetchall()}
    conn.close()
    
    edges = []
    for eid, data in nodes.items():
        if 'terminals' in str(data["path"]):
            continue
        try:
            with open(data["path"], 'r', encoding='utf-8') as f:
                content = f.read()
            deps = list(set(re.findall(r'\\entityref\{([^}]+)\}', content)))
            for dep in deps:
                if dep in nodes:
                    edges.append((eid, dep))
        except Exception:
            pass
            
    return nodes, edges

def topological_sort(nodes, edges):
    graph = defaultdict(list)
    in_degree = {n: 0 for n in nodes}
    
    for u, v in edges:
        if u in nodes and v in nodes:
            graph[v].append(u) # v is dependency of u
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
                
    # Add any nodes that form cycles (should not happen in a DAG, but just in case)
    for n in nodes:
        if in_degree[n] > 0 and n not in sorted_nodes:
            sorted_nodes.append(n)
            
    return sorted_nodes

def translate_to_lean(entity_id, entity_type, tex_content):
    # Extract math formulas
    formulas = re.findall(r'\\\[(.*?)\\\]', tex_content, re.DOTALL)
    if not formulas:
        return ""
        
    math = " ".join(formulas)
    
    # Lexical Translation
    replacements = {
        r'\\mForall\{([^}]+)\}': r'∀ \1, ',
        r'\\mExists\{([^}]+)\}': r'∃ \1, ',
        r'\\mImplies': r'→',
        r'\\mIff': r'↔',
        r'\\mDefIff': r':=',
        r'\\mAnd': r'∧',
        r'\\mOr': r'∨',
        r'\\mNot': r'¬',
        r'\\mIn': r'∈',
        r'\\mSubset': r'⊆',
        r'\\mSet\{([^}]+)\}': r'{\1}',
        r'\\entityref\{[^}]+\}\{(.*?)\}': r'\1',  # Unwrap entityref
        r'\\quad': ' ',
        r'\\text\{([^}]+)\}': r'\1',
        r'\\left': '',
        r'\\right': '',
        r'\\mNorm(?:\[[^\]]*\])?\{([^}]+)\}': r'‖\1‖',
        r'\\mAbs(?:\[[^\]]*\])?\{([^}]+)\}': r'|\1|',
        r'\\mSup(?:\[[^\]]*\])?\{([^}]+)\}': r'⨆ \1',
        r'\\mInf(?:\[[^\]]*\])?\{([^}]+)\}': r'⨅ \1',
        r'\\mDeriv(?:\[[^\]]*\])?\{([^}]+)\}\{([^}]+)\}': r'deriv \1 \2',
        r'\\mIntegral(?:\[[^\]]*\])?\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}': r'∫ \1 \2 \3',
        r'\n': ' ',
    }
    
    lean_math = math
    for pattern, repl in replacements.items():
        lean_math = re.sub(pattern, repl, lean_math)
        
    lean_math = re.sub(r'\s+', ' ', lean_math).strip()
    
    # Format according to type
    lean_name = entity_id.replace('-', '_')
    if entity_type == "axiom":
        return f"axiom {lean_name} : {lean_math}"
    elif entity_type == "object":
        if ":=" in lean_math:
            return f"def {lean_name} : Type := {lean_math.split(':=')[1].strip()}"
        else:
            return f"axiom {lean_name} : Type"
    elif entity_type == "property":
        return f"def {lean_name} : Prop := {lean_math}"
    elif entity_type in ["theorem", "operation"]:
        if ":=" in lean_math:
            return f"theorem {lean_name} : {lean_math.split(':=')[0].strip()} := sorry"
        else:
            return f"axiom {lean_name} : {lean_math}"
            
    return f"-- Unrecognized type for {lean_name}: {lean_math}"

def main():
    print("Exporting Mathesis graph to Lean 4...")
    nodes, edges = get_graph()
    sorted_ids = topological_sort(nodes, edges)
    
    if not sorted_ids:
        print("No entities found.")
        return
        
    if not LEAN_DIR.exists():
        LEAN_DIR.mkdir()
        
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write("import Mathlib\n\n")
        
        for eid in sorted_ids:
            node = nodes[eid]
            try:
                with open(node["path"], 'r', encoding='utf-8') as tex_file:
                    content = tex_file.read()
            except Exception as e:
                print(f"Failed to read {node['path']}: {e}")
                continue
                
            # Strip proof blocks — Lean validates formulations only, not proofs
            content = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', content, flags=re.DOTALL)
            
            lean_code = translate_to_lean(eid, node["type"], content)
            if lean_code:
                f.write(f"-- {eid}\n")
                f.write(f"{lean_code}\n\n")
                
    print(f"Successfully generated {OUT_FILE}")

if __name__ == "__main__":
    main()
