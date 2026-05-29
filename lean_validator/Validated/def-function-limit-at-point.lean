import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

-- Define the limit of a function at a point
def HasLimitAt (f : ℝ → ℝ) (a L : ℝ) : Prop :=
  ∀ ε > 0, ∃ δ > 0, ∀ x, 0 < |x - a| ∧ |x - a| < δ → |f x - L| < ε

theorem def_function_limit_at_point : 
  ∀ (f : ℝ → ℝ) (a : ℝ), 
  (∃ L, HasLimitAt f a L) → 
  ∃ L, HasLimitAt f a L := by sorry