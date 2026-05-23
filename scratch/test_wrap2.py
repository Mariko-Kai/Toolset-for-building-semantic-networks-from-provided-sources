import re

def visual_length(latex_str):
    s = re.sub(r'\\entityref\{[^}]+\}\{([^}]+)\}', r'\1', latex_str)
    s = re.sub(r'\\hypertarget\{[^}]+\}\{\}', '', s)
    s = re.sub(r'\\[a-zA-Z]+text\{([^}]+)\}', r'\1', s)
    s = re.sub(r'\\[a-zA-Z]+', 'X', s)
    # Give some weight to spaces because math mode spaces out operators
    return len(s)

def wrap_formula(formula, max_len=60):
    ops = {
        '\\mIff': 1, '\\mImplies': 2, 
        '\\mOr': 3, '\\And': 4,
        '=': 5, '\\le': 5, '\\ge': 5, '<': 5, '>': 5, '\\approx': 5, '\\sim': 5, '\\equiv': 5,
        '\\colon': 6
    }
    
    # Tokenize LaTeX
    tokens = []
    i = 0
    while i < len(formula):
        if formula[i] == '\\':
            m = re.match(r'\\[a-zA-Z]+', formula[i:])
            if m:
                tokens.append(m.group(0))
                i += len(m.group(0))
            else:
                tokens.append(formula[i:i+2])
                i += 2
        else:
            tokens.append(formula[i])
            i += 1
            
    # Group tokens by brace depth
    depth = 0
    chunks = []
    current_chunk = ""
    for t in tokens:
        if t == '{':
            depth += 1
        elif t == '}':
            depth -= 1
            
        current_chunk += t
        
        # If we are at depth 0, and the token is an operator or a space, we can break AFTER it?
        # Actually we break BEFORE operators.
        # Let's just group tokens into smallest unbreakable units:
        # A unit is either an operator (at depth 0), or a block of non-operators/spaces at depth 0, or everything inside braces.
        # To make it simple, we just keep a list of logical units.
        pass

# Let's use a simpler approach. Just find the operators at depth 0.
def get_breakable_parts(formula):
    ops = [
        '\\\\mIff', '\\\\mImplies', 
        '\\\\mOr', '\\\\And',
        '=', '\\\\le', '\\\\ge', '<', '>', '\\\\approx', '\\\\sim', '\\\\equiv', '\\\\colon'
    ]
    op_regex = re.compile(r'^(' + '|'.join(ops) + r')')
    
    parts = []
    current_part = ""
    i = 0
    depth = 0
    
    while i < len(formula):
        if formula[i] == '{':
            depth += 1
        elif formula[i] == '}':
            depth -= 1
            
        # Check if we are at an operator at depth 0
        if depth == 0:
            m = op_regex.match(formula[i:])
            if m:
                # If we have accumulated text, save it
                if current_part:
                    parts.append(('text', current_part))
                    current_part = ""
                # Save the operator
                parts.append(('op', m.group(0)))
                i += len(m.group(0))
                continue
                
        current_part += formula[i]
        i += 1
        
    if current_part:
        parts.append(('text', current_part))
        
    return parts

def wrap_math(formula, max_len=60):
    parts = get_breakable_parts(formula)
    
    lines = []
    current_line = ""
    
    for ptype, text in parts:
        if ptype == 'op':
            # Check if adding the operator AND the next minimal thing exceeds
            # Actually, just check if adding the operator exceeds.
            # Usually we break BEFORE the operator.
            if current_line and visual_length(current_line + text) > max_len:
                lines.append(current_line)
                current_line = text
            else:
                current_line += text
        else:
            # Text part
            if current_line and visual_length(current_line + text) > max_len:
                # Need to hard break inside text if it's too long?
                # The user said "добавим принудительный перенос, но у этого варианта самый низкий приоритет"
                # Let's see if we can break at commas at depth 0.
                subparts = get_comma_parts(text)
                for sub in subparts:
                    if current_line and visual_length(current_line + sub) > max_len:
                        lines.append(current_line)
                        current_line = sub
                    else:
                        current_line += sub
            else:
                current_line += text
                
    if current_line:
        lines.append(current_line)
        
    # Format
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if not line.startswith('&'):
            formatted_lines.append('& ' + line)
        else:
            formatted_lines.append(line)
            
    return "\\begin{align*}\n" + " \\\\\n".join(formatted_lines) + "\n\\end{align*}"

def get_comma_parts(text):
    # split by comma at depth 0
    parts = []
    current = ""
    depth = 0
    for c in text:
        if c == '{': depth += 1
        elif c == '}': depth -= 1
        
        current += c
        if c == ',' and depth == 0:
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    return parts

test_formula = r"\Forall x \in \entityref{obj-set}{X} \And \Forall y \in \entityref{obj-set}{Y} \colon x \entityref{prop-partial-order}{\le} y \mImplies \mExists c \in \entityref{obj-real-numbers}{\mReal} \Forall x \in \entityref{obj-set}{X}, \Forall y \in \entityref{obj-set}{Y} \colon x \entityref{prop-partial-order}{\le} c \entityref{prop-partial-order}{\le} y"

print(wrap_math(test_formula, max_len=60))
