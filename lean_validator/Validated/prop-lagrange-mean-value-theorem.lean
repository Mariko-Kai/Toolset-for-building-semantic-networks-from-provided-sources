import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem prop_lagrange_mean_value_thm (f : ℝ → ℝ) (a b : ℝ) 
  (h_ab : a < b)
  (h_cont : ContinuousOn f (Set.Icc a b))
  (h_diff : DifferentiableOn ℝ f (Set.Ioo a b)) :
  ∃ c ∈ Set.Ioo a b, f b - f a = (deriv f c) * (b - a) := by sorry