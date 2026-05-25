import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem def_riemann_integral : 
  ∀ (f : ℝ → ℝ) (a b : ℝ), 
  a ≤ b → 
  ContinuousOn f (Set.Icc a b) → 
  ∃ (I : ℝ), (∀ ε > 0, ∃ δ > 0, ∀ (P : List ℝ) (hP : ∀ x ∈ P, x ∈ Set.Icc a b), 
    P.length > 0 → 
    (∀ x ∈ P, |f x| ≤ M) → 
    (∀ x ∈ P, |x - (P.sum / P.length)| < δ) → 
    |I - P.sum * (f (P.sum / P.length))| < ε) ∧ 
  I = ∫ x in a..b, f x := by sorry