import re

def visual_length(latex_str):
    s = re.sub(r'\\entityref\{[^}]+\}\{([^}]+)\}', r'\1', latex_str)
    s = re.sub(r'\\hypertarget\{[^}]+\}\{\}', '', s)
    s = re.sub(r'\\[a-zA-Z]+text\{([^}]+)\}', r'\1', s)
    s = re.sub(r'\\[a-zA-Z]+', 'X', s)
    # Math spaces count as something. Each char left is roughly 1.
    # In math mode, spaces are ignored, but macros like X add some space.
    # We will just count length of string with spaces stripped, and then add 1 for every X.
    s = s.replace(' ', '')
    return len(s)

def wrap_math(formula, max_len=40):
    ops = [
        '\\\\mIff', '\\\\mImplies', 
        '\\\\mOr', '\\\\And',
        '=', '\\\\le', '\\\\ge', '<', '>'
    ]
    op_regex = re.compile(r'^(' + '|'.join(ops) + r')')
    
    # First, parse into chunks at depth 0
    chunks = []
    current_chunk = ""
    i = 0
    depth = 0
    
    while i < len(formula):
        if formula[i] == '{':
            depth += 1
        elif formula[i] == '}':
            depth -= 1
            
        if depth == 0:
            m = op_regex.match(formula[i:])
            if m:
                if current_chunk:
                    chunks.append(('text', current_chunk))
                    current_chunk = ""
                chunks.append(('op', m.group(0)))
                i += len(m.group(0))
                continue
            elif formula[i] == ',':
                # comma
                current_chunk += ','
                chunks.append(('text', current_chunk))
                current_chunk = ""
                i += 1
                continue
                
        current_chunk += formula[i]
        i += 1
        
    if current_chunk:
        chunks.append(('text', current_chunk))
        
    # Now assemble lines
    lines = []
    current_line = ""
    
    for ptype, text in chunks:
        if not current_line:
            current_line = text
        else:
            if visual_length(current_line + text) > max_len:
                if ptype == 'op':
                    # Break BEFORE operator
                    lines.append(current_line)
                    current_line = text
                else:
                    # Break BEFORE text chunk if it was after a comma?
                    # The text chunk might be just " \mExists ..."
                    lines.append(current_line)
                    current_line = text
            else:
                current_line += text
                
    if current_line:
        lines.append(current_line)
        
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if not line.startswith('&'):
            formatted_lines.append('& ' + line)
        else:
            formatted_lines.append(line)
            
    return "\\begin{align*}\n" + " \\\\\n".join(formatted_lines) + "\n\\end{align*}"

test_formula = r"\Forall x \in \entityref{obj-set}{X} \And \Forall y \in \entityref{obj-set}{Y} \colon x \entityref{prop-partial-order}{\le} y \mImplies \mExists c \in \entityref{obj-real-numbers}{\mReal} \Forall x \in \entityref{obj-set}{X}, \Forall y \in \entityref{obj-set}{Y} \colon x \entityref{prop-partial-order}{\le} c \entityref{prop-partial-order}{\le} y"

print(wrap_math(test_formula, 45))
