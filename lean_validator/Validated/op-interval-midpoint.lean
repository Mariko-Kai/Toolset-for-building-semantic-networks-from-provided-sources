import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def op_interval_midpoint : 
  ∀ (a b c : ℝ), c = (a + b) / 2 ↔ ∃ B, B = b ∧ c = (a + B) / 2 := by sorry