import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem def_infimum (s : Set ℝ) : 
  ∃ (inf : ℝ), inf = sInf s ∧ 
  (∀ x ∈ s, inf ≤ x) ∧ 
  (∀ y : ℝ, (∀ x ∈ s, y ≤ x) → inf ≤ y) := by sorry