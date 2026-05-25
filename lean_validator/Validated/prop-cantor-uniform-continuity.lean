import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem prop_cantor_uniform_continuity : 
  ∀ f : ℝ → ℝ, Continuous f → 
  ∀ a b : ℝ, a < b → 
  ∃ P : Set (Set ℝ), 
    (∀ I ∈ P, I ⊆ Set.Icc a b ∧ IsPreconnected I) ∧
    (∀ I J, I ∈ P → J ∈ P → I ≠ J → Disjoint I J) ∧
    (∀ ε > 0, ∃ I ∈ P, ∀ x y, x ∈ I → y ∈ I → abs (f x - f y) < ε) := by sorry