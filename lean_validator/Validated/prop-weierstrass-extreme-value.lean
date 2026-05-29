import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem prop_weierstrass_extreme_value (f : ℝ → ℝ) (a b : ℝ) (hab : a ≤ b) 
  (hf : ContinuousOn f (Set.Icc a b)) : 
  ∃ x ∈ Set.Icc a b, ∀ y ∈ Set.Icc a b, f y ≤ f x := by sorry