import os
import re

CONTENT_DIR = r"f:\Universe\Projects\Учебник по матанализу\content"

# Translation map for section names
SECTION_TRANS = {
    "definition": "Определение",
    "axiom": "Аксиома",
    "statement": "Утверждение",
    "proof": "Доказательство",
    "remark": "Замечание",
    "example": "Пример",
    "corollary": "Следствие"
}

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # Extract metadata
    name_ru = None
    entity_id = None
    
    for line in lines:
        if line.startswith("% name-ru:"):
            name_ru = line.split(":", 1)[1].strip()
        if line.startswith("% entity-id:"):
            entity_id = line.split(":", 1)[1].strip()
            
    if not name_ru or not entity_id:
        print(f"Skipping {filepath} (missing metadata)")
        return

    # Check if already processed (has \subsection{name_ru})
    content = "".join(lines)
    if f"\\subsection{{{name_ru}}}" in content:
        print(f"Skipping {filepath} (already processed)")
        return

    print(f"Processing {filepath} -> {name_ru}")

    new_lines = []
    headers_done = False
    label_moved = False
    
    # We need to find where to insert the subsection (after comments)
    inserted_title = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Keep comments at top
        if not inserted_title and (line.strip().startswith("%") or line.strip() == ""):
            new_lines.append(line)
            i += 1
            continue
            
        # First non-comment line -> Insert Title
        if not inserted_title:
            new_lines.append(f"\n\\subsection{{{name_ru}}}\n")
            new_lines.append(f"\\label{{entity:{entity_id}}}\n\n")
            inserted_title = True
            label_moved = True # We effectively moved the label here
            
        # Process sections
        # Match \section{key}
        match = re.match(r"\\section\{([^}]+)\}", line.strip())
        if match:
            key = match.group(1)
            trans = SECTION_TRANS.get(key.lower(), key.capitalize())
            new_lines.append(f"\\subsubsection*{{{trans}}}\n")
            
            # Check if next line is \label{entity:id}, if so, skip it (moved to top)
            if i + 1 < len(lines):
                next_line = lines[i+1]
                if f"\\label{{entity:{entity_id}}}" in next_line:
                    i += 2 # Skip section and label
                    continue
            i += 1
            continue
            
        # Check for label if it wasn't immediately after section (rare but possible)
        if f"\\label{{entity:{entity_id}}}" in line:
            # We already inserted it at the top
            i += 1
            continue
            
        new_lines.append(line)
        i += 1
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

def main():
    for root, dirs, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex") and file != "master.tex" and file != "mathesis.sty":
                process_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
