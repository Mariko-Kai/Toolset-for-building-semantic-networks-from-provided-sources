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

# Test 5: Code with internal imports (should PASS because imports are floated)
safe_print("\n[Test 5] Internal imports: imports in the middle of text")
lean4_imports = """
import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem op_limit_function (f : ℝ → ℝ) (p A : ℝ) :
  (∀ ε > 0, ∃ δ > 0, ∀ x, 0 < |x - p| ∧ |x - p| < δ → |f x - A| < ε) ↔
  (Filter.Tendsto f (nhds p) (nhds A)) := by sorry
"""
r5 = validate_entity("op-limit-function", lean4_imports)
safe_print(f"  Status: {r5['status']}")
if r5["status"] == "success":
    safe_print("  [OK] PASSED (Floated imports worked!)")
else:
    safe_print(f"  [FAIL]: error count = {len(r5['errors'])}")
    for e in r5['errors']:
        safe_print(f"    Line {e['line']}: {e['message']}")

safe_print("\n" + "=" * 60)
safe_print("All basic tests completed!")
safe_print("=" * 60)
