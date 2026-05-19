import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem thm_rolles_zero_derivative (f : ℝ → ℝ) 
  (hcont : ContinuousOn f (Set.Icc 0 1))
  (hderiv : ∀ x ∈ Set.Ioo 0 1, deriv f x = 0) :
  f 0 = f 1 := by sorry