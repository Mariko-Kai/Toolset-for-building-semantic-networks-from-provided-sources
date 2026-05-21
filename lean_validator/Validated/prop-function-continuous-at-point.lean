import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def prop_function_continuous_at_point : 
  ∀ (f : ℝ → ℝ) (p : ℝ), 
    (∃ L : ℝ, Filter.Tendsto f (nhds p) (nhds L) ∧ L = f p) ↔ 
    (∀ ε > 0, ∃ δ > 0, ∀ x : ℝ, |x - p| < δ → |f x - f p| < ε) := by sorry