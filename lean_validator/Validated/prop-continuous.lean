import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def prop_continuous (f : ℝ → ℝ) (x₀ : ℝ) : 
  (∀ ε > 0, ∃ δ > 0, ∀ x, |x - x₀| < δ → |f x - f x₀| < ε) ↔ 
  ContinuousAt f x₀ := by sorry