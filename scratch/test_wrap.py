import re

def visual_length(latex_str):
    # Remove \entityref{id}{text} -> text
    s = re.sub(r'\\entityref\{[^}]+\}\{([^}]+)\}', r'\1', latex_str)
    # Remove \hypertarget{...}{}
    s = re.sub(r'\\hypertarget\{[^}]+\}\{\}', '', s)
    # Remove formatting \textbf, \mathrm, \mathbf, etc
    s = re.sub(r'\\[a-zA-Z]+text\{([^}]+)\}', r'\1', s)
    # Replace math operators with a rough 1-2 char equivalent
    s = re.sub(r'\\[a-zA-Z]+', 'X', s)
    # Remove spaces
    s = s.replace(' ', '')
    return len(s)

def wrap_formula(formula, max_len=70):
    # Operators to break on (in order of priority: implication -> conjunction -> relation -> basic op)
    ops = [
        r'\\mIff', r'\\mImplies', 
        r'\\And', r'\\mOr', 
        r'=', r'\\le', r'\\ge', r'<', r'>', r'\\approx', r'\\sim', r'\\equiv'
    ]
    
    # We will split the formula using a regex that captures the operators
    # We also want to capture the operator itself so we can keep it
    op_pattern = r'(' + '|'.join(ops) + r')'
    
    parts = re.split(op_pattern, formula)
    
    lines = []
    current_line = ""
    
    for i, part in enumerate(parts):
        # Is this an operator?
        is_op = bool(re.match(op_pattern, part))
        
        # If adding this part exceeds max_len, and current_line is not empty, break
        if current_line and visual_length(current_line + part) > max_len:
            # We must break.
            # If it's an operator, it starts the new line.
            if is_op:
                lines.append(current_line)
                current_line = part
            else:
                # If it's not an operator, maybe we can break BEFORE it?
                # But it's better to break BEFORE the previous operator.
                # Since we split by operators, 'part' is a non-operator chunk.
                # If this chunk itself is too long, we need a hard break inside it.
                if visual_length(part) > max_len:
                    # Hard break logic (break at space or comma)
                    subparts = re.split(r'(,| )', part)
                    for sub in subparts:
                        if visual_length(current_line + sub) > max_len and current_line:
                            lines.append(current_line)
                            current_line = sub
                        else:
                            current_line += sub
                else:
                    lines.append(current_line)
                    current_line = part
        else:
            current_line += part
            
    if current_line:
        lines.append(current_line)
        
    # Now format with align*
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if not line: continue
        # Prepend & to align all lines
        if not line.startswith('&'):
            formatted_lines.append('& ' + line)
        else:
            formatted_lines.append(line)
            
    return "\\begin{align*}\n" + " \\\\\n".join(formatted_lines) + "\n\\end{align*}"

test_formulas = [
    r"\Forall x \in \entityref{obj-set}{X} \And \Forall y \in \entityref{obj-set}{Y} \colon x \entityref{prop-partial-order}{\le} y \mImplies \mExists c \in \entityref{obj-real-numbers}{\mReal} \Forall x \in \entityref{obj-set}{X}, \Forall y \in \entityref{obj-set}{Y} \colon x \entityref{prop-partial-order}{\le} c \entityref{prop-partial-order}{\le} y"
]

for tf in test_formulas:
    print(wrap_formula(tf, 70))
