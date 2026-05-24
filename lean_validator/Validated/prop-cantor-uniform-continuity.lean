import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem cantor_uniform_continuity (a b : ℝ) (hab : a ≤ b) (f : ℝ → ℝ) 
  (hf : ContinuousOn f (Set.Icc a b)) :
  ∀ ε > 0, ∃ (P : Finset (Set ℝ)), 
    (∀ I ∈ P, ∃ c d : ℝ, c ≤ d ∧ I = Set.Icc c d) ∧
    (⋃ I ∈ P, I) = Set.Icc a b ∧
    (∀ I ∈ P, ∀ x y, x ∈ I → y ∈ I → |f x - f y| < ε) := by sorry