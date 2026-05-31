import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem prop_cauchys_mean_value_theorem (f : ℝ → ℝ) (a b : ℝ) (hab : a < b) 
  (hf_cont : ContinuousOn f (Set.Icc a b)) 
  (hf_diff : DifferentiableOn ℝ f (Set.Ioo a b)) :
  ∃ c ∈ Set.Ioo a b, deriv f c = (f b - f a) / (b - a) := by sorry