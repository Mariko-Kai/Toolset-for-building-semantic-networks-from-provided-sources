import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem cantor_uniform_continuity (a b : ℝ) (hab : a ≤ b) :
  ∀ f : ℝ → ℝ, ContinuousOn f (Set.Icc a b) →
  ∀ ε > 0, ∃ P : Set (Set ℝ), 
    (∀ I ∈ P, I ⊆ Set.Icc a b ∧ ∃ x y, I = Set.Icc x y ∧ x ≤ y) ∧
    (∀ I ∈ P, ∀ x y, x ∈ I → y ∈ I → |f x - f y| < ε) := by sorry