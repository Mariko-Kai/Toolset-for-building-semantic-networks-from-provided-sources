import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem thm_cauchy_criterion_limit_base 
  (X : Type*) 
  (B : Set (Set X)) 
  (f : X → ℝ) 
  (hB : ∀ B' ∈ B, B'.Nonempty) 
  (hB_base : ∀ x : X, ∃ B' ∈ B, x ∈ B') : 
  (∃ A : ℝ, ∀ ε > 0, ∃ B' ∈ B, ∀ x ∈ B', |f x - A| < ε) ↔ 
  (∀ ε > 0, ∃ B' ∈ B, ∀ x₁ x₂ : X, x₁ ∈ B' → x₂ ∈ B' → |f x₁ - f x₂| < ε) := by sorry