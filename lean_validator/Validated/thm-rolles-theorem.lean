import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem thm_rolles_theorem (f : ℝ → ℝ) (a b : ℝ) (hab : a < b) 
  (hcont : ContinuousOn f (Set.Icc a b))
  (hdiff : DifferentiableOn ℝ f (Set.Ioo a b))
  (heq : f a = f b) :
  ∃ c ∈ Set.Ioo a b, deriv f c = 0 := by sorry