import os
import re
import sys
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mathesis import MathesisDB
from mathesis.models import Axiom, Object, Property, Operation, Theorem

CONTENT_DIR = PROJECT_ROOT / "content"
DB_PATH = PROJECT_ROOT / "mathesis_index.db"

def clean_latex(text: str) -> str:
    if not text:
        return ""
    # Strip \label{...}
    text = re.sub(r'\\label\{.*?\}', '', text)
    
    # Normalize double-escaped empty set symbol
    text = text.replace('\\\\varnothing', '\\varnothing')
    
    # Strip comments (lines or parts of lines starting with %)
    lines = []
    for line in text.split('\n'):
        # Split at the first unescaped %
        parts = re.split(r'(?<!\\)%', line, maxsplit=1)
        clean_line = parts[0].strip()
        if clean_line:
            lines.append(clean_line)
    return '\n'.join(lines).strip()

def main():
    print("=== Reseeding Web Database Tables ===")
    
    # 1. Initialize MathesisDB and reset tables
    kb = MathesisDB(str(DB_PATH))
    kb.reset_db()
    
    conn = kb.conn
    
    # Track all entity types to do relationship insertion in second pass
    entity_types = {} # entity_id -> entity_type
    entity_files = {} # entity_id -> file_content
    processed_ids = set()
    
    # Pass 1: Insert core entities
    for root, dirs, files in os.walk(CONTENT_DIR):
        for file in files:
            if not file.endswith(".tex") or file in ("master.tex", "mathesis.sty", "TEMPLATE.tex"):
                continue
            
            filepath = Path(root) / file
            
            # Skip terminals
            if "terminals" in filepath.parts:
                continue
                
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Parse ID and Type
            id_match = re.search(r'% entity-id:\s*(.*)', content)
            if not id_match:
                # Try from filename: title [id].tex
                fn_match = re.search(r'\[([^\]]+)\]\.tex$', file)
                entity_id = fn_match.group(1).strip() if fn_match else None
            else:
                entity_id = id_match.group(1).strip()
                
            if not entity_id:
                continue
                
            # Skip duplicates
            if entity_id in processed_ids:
                print(f"  Skipping duplicate entity {entity_id} from {filepath.name}")
                continue
                
            type_match = re.search(r'% entity-type:\s*(.*)', content)
            if not type_match:
                # Determine from directory
                rel = filepath.relative_to(CONTENT_DIR).parts[0]
                type_map = {
                    "foundations": "axiom", 
                    "objects": "object", 
                    "properties": "property",
                    "operations": "operation", 
                    "theorems": "theorem"
                }
                entity_type = type_map.get(rel, "unknown")
            else:
                entity_type = type_match.group(1).strip().lower()
                # Map abbreviated types
                if entity_type == 'def' or entity_type == 'definition':
                    entity_type = 'object'
                elif entity_type == 'prop':
                    entity_type = 'property'
                elif entity_type == 'thm':
                    entity_type = 'theorem'
                elif entity_type == 'op':
                    entity_type = 'operation'
                    
            if entity_type not in ("axiom", "object", "property", "operation", "theorem"):
                continue
                
            entity_types[entity_id] = entity_type
            entity_files[entity_id] = (filepath, content)
            processed_ids.add(entity_id)
            
            # Parse module
            mod_match = re.search(r'% module:\s*(.*)', content)
            module = mod_match.group(1).strip() if mod_match else "mathematical_analysis"
            
            # Parse name-ru (Russian title)
            name_match = re.search(r'% name-ru:\s*(.*)', content)
            if name_match:
                name = name_match.group(1).strip()
            else:
                # Try environment title
                env_match = re.search(r'\\begin\{' + entity_type + r'\}\[([^\]]+)\]', content)
                if env_match:
                    name = env_match.group(1).strip()
                else:
                    # Parse from filename
                    fn_title_match = re.search(r'^(.*?)\s*\[', file)
                    name = fn_title_match.group(1).strip() if fn_title_match else entity_id
                    
            # Parse description (intuition)
            desc_match = re.search(r'\\textbf\{Описание:\}\s*(.*?)(?=\\begin\{|\Z)', content, re.DOTALL)
            intuition = clean_latex(desc_match.group(1).strip()) if desc_match else ""
            
            # Extract formal definition / statement block
            block_match = re.search(
                r'\\begin\{' + entity_type + r'\}(?:\[.*?\])?\s*(.*?)\s*\\end\{' + entity_type + r'\}',
                content, re.DOTALL
            )
            if block_match:
                statement = clean_latex(block_match.group(1).strip())
            else:
                statement = clean_latex(content)
                
            rel_path = str(filepath.relative_to(PROJECT_ROOT))
            
            # Insert into database using models
            if entity_type == "axiom":
                # system: ZFC or FOL or Tool
                system = "ZFC"
                if "fol" in entity_id or "logical" in entity_id:
                    system = "FOL"
                ax = Axiom(id=entity_id, name=name, system=system, statement=statement, file_path=rel_path)
                kb.create_axiom(ax)
                
            elif entity_type == "object":
                obj = Object(id=entity_id, name=name, module=module, formal_definition=statement, intuition=intuition, file_path=rel_path)
                kb.create_object(obj)
                
            elif entity_type == "property":
                prop = Property(id=entity_id, name=name, module=module, formal_definition=statement, file_path=rel_path)
                kb.create_property(prop)
                
            elif entity_type == "operation":
                op = Operation(id=entity_id, name=name, module=module, arity=1, formal_definition=statement, file_path=rel_path)
                kb.create_operation(op)
                
            elif entity_type == "theorem":
                # Parse proof
                proof_match = re.search(r'\\begin\{proof\}\s*(.*?)\s*\\end\{proof\}', content, re.DOTALL)
                proof = clean_latex(proof_match.group(1).strip()) if proof_match else ""
                
                # Check if it is a lemma or theorem
                subtype = "theorem"
                if "lemma" in entity_id:
                    subtype = "lemma"
                
                thm = Theorem(id=entity_id, name=name, subtype=subtype, module=module, statement=statement, proof=proof, file_path=rel_path)
                kb.create_theorem(thm)
                
            # Populate FTS search index
            conn.execute(
                "INSERT INTO entity_fts (entity_id, entity_type, name, content) VALUES (?, ?, ?, ?)",
                (entity_id, entity_type, name, f"{name} {statement} {intuition}")
            )
            
            print(f"  Indexed [{entity_type}]: {entity_id}")
            
    # Pass 2: Establish relationships
    print("\n--- Establishing Relationships ---")
    for entity_id, (filepath, content) in entity_files.items():
        entity_type = entity_types[entity_id]
        
        # Scan for dependencies (\entityref{dep_id}{...})
        deps = list(set(re.findall(r'\\entityref\{([^}]+)\}', content)))
        
        # Also parse macro dependencies
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
            concrete = re.findall(rf'{escaped}\[([^\]]+)\]', content)
            if concrete:
                deps.extend(concrete)
            elif re.search(rf'{escaped}(?!\[)\{{', content):
                deps.append(default_id)
                
        deps = list(set(deps))
        
        for dep_id in deps:
            if dep_id == entity_id or dep_id not in entity_types:
                continue
                
            dep_type = entity_types[dep_id]
            
            if entity_type == "theorem":
                if dep_type == "axiom":
                    kb.link_theorem_axiom(entity_id, dep_id)
                elif dep_type == "object":
                    kb.link_theorem_object(entity_id, dep_id)
                elif dep_type == "property":
                    kb.link_theorem_property(entity_id, dep_id)
                elif dep_type == "operation":
                    kb.link_theorem_operation(entity_id, dep_id)
                elif dep_type == "theorem":
                    kb.link_theorem_dependency(entity_id, dep_id)
                    
            elif entity_type == "object" and dep_type == "property":
                kb.link_object_property(entity_id, dep_id)
                
    conn.commit()
    print("Reseed complete! Web database successfully populated.")

if __name__ == "__main__":
    main()
