import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem def_function_uniformly_continuous : 
  ∃ f : ℝ → ℝ, UniformContinuousOn f (Set.Icc 0 1) ∧ 
  ∃ M : ℝ, ∀ x ∈ Set.Icc 0 1, |f x| ≤ M := by sorry