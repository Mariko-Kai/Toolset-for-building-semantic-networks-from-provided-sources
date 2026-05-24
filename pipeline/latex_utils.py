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
