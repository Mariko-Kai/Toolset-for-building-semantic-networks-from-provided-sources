import Mathlib

def def_function_uniformly_continuous (f : ℝ → ℝ) : 
  ∀ ε > 0, ∃ δ > 0, ∀ x y : ℝ, |x - y| < δ → |f x - f y| < ε := by sorry
