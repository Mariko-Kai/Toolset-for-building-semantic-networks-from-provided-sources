import os
import re

CONTENT_DIR = r"f:\Universe\Projects\Учебник по матанализу\content"

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Pattern to find section labels and wrap subsequent content
    # We assume content starts after \label{...} and ends before next \section or end of file
    # We want to wrap the content in \[ ... \]
    
    # Simple heuristic: split by \section
    parts = re.split(r'(\\section\{[^}]+\})', content)
    
    new_content = ""
    # parts[0] is header (entity metadata)
    new_content += parts[0]
    
    for i in range(1, len(parts), 2):
        header = parts[i] # \section{...}
        body = parts[i+1]
        
        # Check if body has \label
        match_label = re.search(r'(\\label\{[^}]+\})', body)
        if match_label:
            label = match_label.group(1)
            rest = body[match_label.end():]
            
            # Trim whitespace
            rest = rest.strip()
            
            if not rest:
                new_content += header + body
                continue
                
            # Check if already wrapped (basic check)
            if rest.startswith('\\[') or rest.startswith('$'):
                new_content += header + body
                continue
            
            # Wrap in \[ \]
            # We need to preserve the \square if it exists
            # Actually, standard is \square is part of the formula?
            # PROTOCOL says: ... \;\square
            # So yes.
            
            # If body has proofs, we might need to be careful.
            # But currently I only wrote definitions and properties with proofs.
            # Proofs are \section{proof}? Or just text?
            # My De Morgan has \section{proof}.
            # So splitting by \section works.
            
            # Special case for 'proof' section: usually proof environment or text with math.
            if "proof" in header:
                 # Proofs might involve text and math mixed.
                 # De Morgan proof: \text{...} \begin{aligned} ... \end{aligned}
                 # If I wrap everything in \[, \text is fine.
                 # But aligned inside \[ \] is fine.
                 # Let's wrap proofs too for now if they look like math-heavy.
                 pass

            wrapped_rest = f"\n\\[\n{rest}\n\\]\n"
            new_content += header + f"\n{label}" + wrapped_rest
        else:
            new_content += header + body

    if new_content != content:
        print(f"Fixing {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

def main():
    for root, dirs, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex") and file != "master.tex" and file != "mathesis.sty":
                fix_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
