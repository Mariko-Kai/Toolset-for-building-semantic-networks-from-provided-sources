import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem def_real_analysis_infinitesimal : 
  ∃ (IsInfinitesimal : ℝ → Prop), 
    ∀ x : ℝ, IsInfinitesimal x ↔ (x ≠ 0 ∧ ∀ r : ℝ, r > 0 → |x| < r) := by sorry