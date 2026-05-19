import re
from pathlib import Path

log_path = Path("logs/synthesis/lean/2026-05-17_21-11-44_prop-limit-point_attempt_1.txt")
content = log_path.read_text(encoding="utf-8")

# Extract the response section
def extract_lean_code_blocks(response: str, prompt_ends_in_code_block: bool = False) -> list:
    parts = re.split(r'```(?:lean|lean4)?\s*', response, flags=re.IGNORECASE)
    blocks = []
    if prompt_ends_in_code_block:
        if parts[0].strip():
            blocks.append(parts[0].strip())
        for i in range(2, len(parts), 2):
            blocks.append(parts[i].strip())
    else:
        for i in range(1, len(parts), 2):
            blocks.append(parts[i].strip())
            
    if not blocks:
        clean = re.sub(r'^```(?:lean|lean4)?\s*', '', response, flags=re.MULTILINE | re.IGNORECASE)
        clean = re.sub(r'^```\s*$', '', clean, flags=re.MULTILINE)
        if clean.strip():
            blocks.append(clean.strip())
    return blocks

response_match = re.search(r"=== RESPONSE ===\n(.*)", content, re.DOTALL)
if response_match:
    response = response_match.group(1).strip()
    print("Raw response length:", len(response))
    
    # Test normal extraction
    blocks_normal = extract_lean_code_blocks(response, False)
    print("\n--- Normal Extraction (False) ---")
    print("Found blocks:", len(blocks_normal))
    for i, b in enumerate(blocks_normal):
        print(f"Block {i} contains def:", "def" in b)
        print(f"Block {i} preview:", repr(b[:100]))
        
    # Test prefix-forced extraction (since our prompt ends in ```lean4\ndef prop_limit_point)
    blocks_forced = extract_lean_code_blocks(response, True)
    print("\n--- Prefix-Forced Extraction (True) ---")
    print("Found blocks:", len(blocks_forced))
    for i, b in enumerate(blocks_forced):
        print(f"Block {i} contains def:", "def" in b)
        print(f"Block {i} preview:", repr(b[:100]))
else:
    print("Response not found in log.")
