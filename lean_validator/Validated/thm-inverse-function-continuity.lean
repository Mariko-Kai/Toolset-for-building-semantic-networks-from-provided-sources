import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem thm_inverse_function_continuity (a b c d : ℝ) (f : ℝ → ℝ) (g : ℝ → ℝ) 
  (hf : ∀ x ∈ Set.Icc a b, f x ∈ Set.Icc c d)
  (hg : ∀ y ∈ Set.Icc c d, g y ∈ Set.Icc a b)
  (hfg : ∀ x ∈ Set.Icc a b, g (f x) = x)
  (hgf : ∀ y ∈ Set.Icc c d, f (g y) = y) :
  ∀ y₀ ∈ Set.Ioo c d, ContinuousAt g y₀ := by sorry