import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem def_limit_function_base : 
  ∃ (limit_function : (ℝ → ℝ) → ℝ → ℝ), 
    ∀ (f : ℝ → ℝ) (a : ℝ), 
      ∀ ε > 0, ∃ δ > 0, ∀ x, 0 < |x - a| ∧ |x - a| < δ → |f x - limit_function f a| < ε := by sorry