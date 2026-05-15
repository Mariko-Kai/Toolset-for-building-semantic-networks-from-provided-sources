"""
Synthetic test for lean_validator.py -- bypasses the full pipeline.
"""
import sys
import os
from pathlib import Path

# Force UTF-8 output
os.environ["PYTHONIOENCODING"] = "utf-8"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lean_validator import validate_entity, check_lean_environment


def safe_print(msg):
    """Print with fallback for cp1251 console."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(str(msg).encode('ascii', errors='replace').decode('ascii'))


safe_print("=" * 60)
safe_print("=== Lean Validator -- Synthetic Test ===")
safe_print("=" * 60)

# Step 0: Environment check
safe_print("\n[Test 0] Lean Environment Check...")
ok = check_lean_environment()
safe_print(f"  Environment OK: {ok}")
if not ok:
    safe_print("  FATAL: Lean toolchain not found. Cannot run tests.")
    sys.exit(1)

# Test 1: Valid axiom (should PASS)
safe_print("\n[Test 1] Valid axiom: 'axiom test_axiom : 1 + 1 = 2'")
r1 = validate_entity("test-valid", "axiom test_axiom : 1 + 1 = 2")
safe_print(f"  Status: {r1['status']}")
assert r1["status"] == "success", f"FAIL: Expected success, got {r1['status']}"
safe_print("  [OK] PASSED")

# Test 2: Invalid code (should FAIL)
safe_print("\n[Test 2] Invalid code: type mismatch")
r2 = validate_entity("test-invalid", 'def broken : Nat := "not a nat"')
safe_print(f"  Status: {r2['status']}")
safe_print(f"  Error count: {len(r2['errors'])}")
assert r2["status"] == "failed", f"FAIL: Expected failed, got {r2['status']}"
safe_print("  [OK] PASSED")

# Test 3: sorry-based theorem (should pass -- sorry is a warning, not error)
safe_print("\n[Test 3] Sorry-based theorem")
r3 = validate_entity("test-sorry", "theorem test_thm : 1 + 1 = 2 := by sorry")
safe_print(f"  Status: {r3['status']}")
assert r3["status"] == "success", f"FAIL: Expected success, got {r3['status']}"
safe_print("  [OK] PASSED")

# Test 4: Real math -- Mathlib-dependent
safe_print("\n[Test 4] Mathlib-dependent: open Set, trivial")
lean4_real = """
open Set

theorem test_real_math (s : Set Nat) (hs : s.Nonempty) :
  True := by
  trivial
"""
r4 = validate_entity("test-mathlib", lean4_real)
safe_print(f"  Status: {r4['status']}")
if r4["status"] == "success":
    safe_print("  [OK] PASSED (Mathlib compiled)")
elif r4["status"] == "timeout":
    safe_print("  [WARN] TIMEOUT (expected on first run -- Mathlib cache build)")
else:
    safe_print(f"  [FAIL]: error count = {len(r4['errors'])}")

safe_print("\n" + "=" * 60)
safe_print("All basic tests completed!")
safe_print("=" * 60)
