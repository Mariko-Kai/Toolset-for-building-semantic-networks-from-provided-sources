import sys
import logging

logging.basicConfig(level=logging.DEBUG)

sys.path.append('f:/Universe/Projects/Учебник по матанализу')
from pipeline.lean_validator import LeanReplManager, discover_mathlib_signatures

print("Getting instance...")
repl = LeanReplManager.get_instance()
print("Discovering signatures...")
sigs = discover_mathlib_signatures(['Nat.add', 'Real.cos'])
print(f"Signatures: {sigs}")
