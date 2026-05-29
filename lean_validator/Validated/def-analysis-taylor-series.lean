import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem taylor_series_representation (f : ℝ → ℝ) (a : ℝ) (r : ℝ) (hr : 0 < r) 
  (hf : ContDiff ℝ ⊤ f) :
  ∀ x ∈ Set.Ioo (a - r) (a + r), 
    f x = ∑' k : ℕ, (iteratedDeriv k f a / (k.factorial : ℝ)) * (x - a) ^ k := by sorry