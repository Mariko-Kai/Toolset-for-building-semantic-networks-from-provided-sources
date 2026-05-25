import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MACROS_FILE = PROJECT_ROOT / "content" / "mathesis_macros.sty"

_MACRO_MAP = None
_MACRO_METADATA = None

def get_macro_metadata() -> dict:
    """Reads all .tex files in content/ and returns a dict mapping entity_id to its macro metadata."""
    global _MACRO_METADATA
    if _MACRO_METADATA is not None:
        return _MACRO_METADATA

    _MACRO_METADATA = {}
    content_dir = PROJECT_ROOT / "content"
    if not content_dir.exists():
        return _MACRO_METADATA

    pattern = re.compile(r'^%\s*(macro|notation|args|entity-id):\s*(.+)$', re.MULTILINE)

    for root, _, files in os.walk(content_dir):
        for f in files:
            if f.endswith('.tex'):
                file_path = os.path.join(root, f)
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read(2048) # Header is always at the top
                    
                    meta_dict = {}
                    for match in pattern.finditer(content):
                        key = match.group(1).strip()
                        val = match.group(2).strip()
                        meta_dict[key] = val
                        
                    if 'entity-id' in meta_dict and 'macro' in meta_dict:
                        eid = meta_dict['entity-id']
                        _MACRO_METADATA[eid] = {
                            'macro': meta_dict['macro'],
                            'notation': meta_dict.get('notation', ''),
                            'args': meta_dict.get('args', '0')
                        }
    return _MACRO_METADATA

def get_macro_to_id_mapping():
    """Reads mathesis_macros.sty and returns a dict mapping \\MacroName -> entity_id."""
    global _MACRO_MAP
    if _MACRO_MAP is not None:
        return _MACRO_MAP

    _MACRO_MAP = {}
    if not MACROS_FILE.exists():
        return _MACRO_MAP

    with open(MACROS_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # Match: \newcommand{\MacroName}[args]{\hyperlink{entity-id}
    # OR \newcommand{\MacroName}{\hyperlink{entity-id}
    # Including optional \mathopen{} wrapper: \newcommand{\MacroName}{\mathopen{\hyperlink{entity-id}
    pattern = r'\\newcommand\{\\([a-zA-Z0-9_]+)\}(?:\[\d+\])?\{.*?\\hyperlink\{([a-zA-Z0-9_-]+)\}'
    
    for match in re.finditer(pattern, content):
        macro_name = match.group(1)
        entity_id = match.group(2)
        _MACRO_MAP[macro_name] = entity_id

    return _MACRO_MAP

def extract_dependencies(tex_content: str) -> list[str]:
    """
    Parses a LaTeX string and extracts all dependencies (entity-ids).
    It looks for semantic macros defined in mathesis_macros.sty.
    """
    deps = set()
    
    # 1. Look for explicit \hyperlink{id}{...} just in case
    explicit_links = re.findall(r'\\hyperlink\{([^{}]+)\}', tex_content)
    for link in explicit_links:
        deps.add(link)
        
    # 2. Look for semantic macros (e.g. \RealNumbers)
    macro_map = get_macro_to_id_mapping()
    
    # Simple search for any \MacroName word boundary in text
    for macro_name, entity_id in macro_map.items():
        # Match \MacroName followed by non-alpha character or end of string
        pattern = r'\\' + re.escape(macro_name) + r'(?![a-zA-Z])'
        if re.search(pattern, tex_content):
            deps.add(entity_id)

    return list(deps)

def format_long_formulas(text: str, max_len=50) -> str:
    """
    Parses LaTeX text, finds display math blocks \[ ... \], and formats long formulas
    by wrapping them in \begin{aligned} and breaking at safe operator boundaries.
    """
    def process_block(match):
        inner = match.group(1).strip()
        if len(inner) < max_len or "\\begin{aligned}" in inner or "\\begin{split}" in inner:
            return f"\\[\n{inner}\n\\]"
            
        # Protect standard brackets from breaking errors inside aligned blocks
        inner = re.sub(r'\\left\s*([()\[\]|])', r'\\Biggl\1', inner)
        inner = re.sub(r'\\left\\\{', r'\\Biggl\\{', inner)
        inner = re.sub(r'\\right\s*([()\[\]|])', r'\\Biggr\1', inner)
        inner = re.sub(r'\\right\\\}', r'\\Biggr\\}', inner)
        
        # Split tokens safely, keeping track of braces depth to avoid breaking arguments
        tokens = re.split(r'(\\[a-zA-Z]+|\{|\})', inner)
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MACROS_FILE = PROJECT_ROOT / "content" / "mathesis_macros.sty"

_MACRO_MAP = None
_MACRO_METADATA = None

def get_macro_metadata() -> dict:
    """Reads all .tex files in content/ and returns a dict mapping entity_id to its macro metadata."""
    global _MACRO_METADATA
    if _MACRO_METADATA is not None:
        return _MACRO_METADATA

    _MACRO_METADATA = {}
    content_dir = PROJECT_ROOT / "content"
    if not content_dir.exists():
        return _MACRO_METADATA

    pattern = re.compile(r'^%\s*(macro|notation|args|entity-id):\s*(.+)$', re.MULTILINE)

    for root, _, files in os.walk(content_dir):
        for f in files:
            if f.endswith('.tex'):
                file_path = os.path.join(root, f)
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read(2048) # Header is always at the top
                    
                    meta_dict = {}
                    for match in pattern.finditer(content):
                        key = match.group(1).strip()
                        val = match.group(2).strip()
                        meta_dict[key] = val
                        
                    if 'entity-id' in meta_dict and 'macro' in meta_dict:
                        eid = meta_dict['entity-id']
                        _MACRO_METADATA[eid] = {
                            'macro': meta_dict['macro'],
                            'notation': meta_dict.get('notation', ''),
                            'args': meta_dict.get('args', '0')
                        }
    return _MACRO_METADATA

def get_macro_to_id_mapping():
    """Reads mathesis_macros.sty and returns a dict mapping \\MacroName -> entity_id."""
    global _MACRO_MAP
    if _MACRO_MAP is not None:
        return _MACRO_MAP

    _MACRO_MAP = {}
    if not MACROS_FILE.exists():
        return _MACRO_MAP

    with open(MACROS_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # Match: \newcommand{\MacroName}[args]{\hyperlink{entity-id}
    # OR \newcommand{\MacroName}{\hyperlink{entity-id}
    # Including optional \mathopen{} wrapper: \newcommand{\MacroName}{\mathopen{\hyperlink{entity-id}
    pattern = r'\\newcommand\{\\([a-zA-Z0-9_]+)\}(?:\[\d+\])?\{.*?\\hyperlink\{([a-zA-Z0-9_-]+)\}'
    
    for match in re.finditer(pattern, content):
        macro_name = match.group(1)
        entity_id = match.group(2)
        _MACRO_MAP[macro_name] = entity_id

    return _MACRO_MAP

def extract_dependencies(tex_content: str) -> list[str]:
    """
    Parses a LaTeX string and extracts all dependencies (entity-ids).
    It looks for semantic macros defined in mathesis_macros.sty.
    """
    deps = set()
    
    # 1. Look for explicit \hyperlink{id}{...} just in case
    explicit_links = re.findall(r'\\hyperlink\{([^{}]+)\}', tex_content)
    for link in explicit_links:
        deps.add(link)
        
    # 2. Look for semantic macros (e.g. \RealNumbers)
    macro_map = get_macro_to_id_mapping()
    
    # Simple search for any \MacroName word boundary in text
    for macro_name, entity_id in macro_map.items():
        # Match \MacroName followed by non-alpha character or end of string
        pattern = r'\\' + re.escape(macro_name) + r'(?![a-zA-Z])'
        if re.search(pattern, tex_content):
            deps.add(entity_id)

    return list(deps)

import math

def format_long_formulas(text: str, max_page_width=90) -> str:
    r"""
    Parses LaTeX text, finds display math blocks \[ ... \], and dynamically formats long formulas
    by calculating total visual length and balancing the lines evenly in a \begin{flalign*} block.
    """
    def process_block(match):
        inner = match.group(1).strip()
        if "\\begin{aligned}" in inner or "\\begin{split}" in inner:
            return f"\\[\n{inner}\n\\]"
            
        # Protect standard brackets from breaking errors inside aligned blocks
        inner = re.sub(r'\\left\s*([()\[\]|])', r'\\Biggl\1', inner)
        inner = re.sub(r'\\left\\\{', r'\\Biggl\\{', inner)
        inner = re.sub(r'\\right\s*([()\[\]|])', r'\\Biggr\1', inner)
        inner = re.sub(r'\\right\\\}', r'\\Biggr\\}', inner)
        
        # Split tokens safely
        tokens = re.split(r'(\\[a-zA-Z]+|\{|\})', inner)
        
        # Calculate visual length of each token
        token_vis_lens = []
        for t in tokens:
            if not t:
                token_vis_lens.append(0)
            elif t in ('{', '}'):
                token_vis_lens.append(0)
            elif t.startswith('\\'):
                if t in ('\\quad', '\\qquad'): token_vis_lens.append(4)
                elif t.startswith('\\text'): token_vis_lens.append(10)
                else: token_vis_lens.append(1) # Most macros render as 1 char
            else:
                token_vis_lens.append(len(t))
                
        total_vis_len = sum(token_vis_lens)
        
        # Dynamic calculation: balance lines evenly
        num_lines = max(1, math.ceil(total_vis_len / max_page_width))
        if num_lines <= 1:
            return f"\\[\n{inner}\n\\]"
            
        target_len = total_vis_len / num_lines
        
        depth = 0
        current_line = ["& "]
        lines = []
        break_ops = {'\\TermImplication', '\\TermEquivalence', '\\TermConjunction', '\\TermDisjunction', '\\Rightarrow', '\\Leftrightarrow', '\\land', '\\lor'}
        break_quantifiers = {'\\TerForall', '\\TermExists', '\\forall', '\\exists'}
        
        current_len = 0
        for token, vis_len in zip(tokens, token_vis_lens):
            if not token: continue
            if token == '{': depth += 1
            elif token == '}': depth -= 1
            
            if depth == 0 and (token in break_ops or token in break_quantifiers):
                if current_len >= target_len:
                    lines.append("".join(current_line).strip())
                    if token in break_ops:
                        current_line = ["& \\quad " + token]
                    else:
                        current_line = ["& " + token]
                    current_len = vis_len # reset counter to the length of the operator
                else:
                    current_line.append(token)
                    current_len += vis_len
            else:
                current_line.append(token)
                current_len += vis_len
                
        if current_line:
            lines.append("".join(current_line).strip())
            
        # Remove empty lines if any
        lines = [l for l in lines if l and l.strip() not in ('&', '& \\quad')]
            
        if len(lines) <= 1:
            inner_stripped = lines[0][2:].strip() if lines and lines[0].startswith("& ") else inner
            return f"\\[\n{inner_stripped}\n\\]"

        # Use flalign* with trailing & to force the block to the left margin
        aligned_inner = " & \\\\\n".join(lines) + " &"
        return f"\\begin{{flalign*}}\n{aligned_inner}\n\\end{{flalign*}}"

    return re.sub(r'\\\[(.*?)\\\]', process_block, text, flags=re.DOTALL)
