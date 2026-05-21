import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def prop_function_uniformly_continuous (f : ℝ → ℝ) (E : Set ℝ) : Prop :=
  ∀ ε > 0, ∃ δ > 0, ∀ x₁ ∈ E, ∀ x₂ ∈ E, |x₁ - x₂| < δ → |f x₁ - f x₂| < ε