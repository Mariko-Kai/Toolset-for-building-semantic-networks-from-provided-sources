import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem thm_cauchy_criterion_vector_valued (X : Type*) [Nonempty X] (n : ℕ) (f : X → (Fin n → ℝ)) :
  ∀ L : (Fin n → ℝ), (∀ x : X, f x = L) ↔ 
  ∀ ε > 0, ∃ B : Set X, ∀ x₁ x₂ : X, x₁ ∈ B → x₂ ∈ B → 
    ‖f x₁ - f x₂‖ < ε := by sorry