import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem Weierstrass_extreme_value (a b : ℝ) (hab : a ≤ b) (f : ℝ → ℝ) 
  (hf : ContinuousOn f (Set.Icc a b)) :
  ∃ c d : ℝ, c ∈ Set.Icc a b ∧ d ∈ Set.Icc a b ∧ 
  f c = sSup (f '' Set.Icc a b) ∧ f d = sInf (f '' Set.Icc a b) := by sorry