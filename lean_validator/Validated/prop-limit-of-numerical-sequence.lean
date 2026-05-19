import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsLimit (a : ℕ → ℝ) (L : ℝ) : Prop :=
  ∀ ε > 0, ∃ N : ℕ, ∀ n : ℕ, n > N → |a n - L| < ε

theorem IsLimit_eq (a : ℕ → ℝ) (L : ℝ) : 
  (∀ ε > 0, ∃ N : ℕ, ∀ n : ℕ, n > N → |a n - L| < ε) ↔ 
  Filter.Tendsto a Filter.atTop (nhds L) := by sorry