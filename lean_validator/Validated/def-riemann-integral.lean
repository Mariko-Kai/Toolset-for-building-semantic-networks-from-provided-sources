import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem def_riemann_integral (f : ℝ → ℝ) (a b : ℝ) (hab : a ≤ b) (hf : ContinuousOn f (Set.Icc a b)) :
  ∃ I : ℝ, (∀ ε > 0, ∃ δ > 0, ∀ (P : ℝ × ℝ), 
    -- P represents a partition of [a,b] with mesh < δ
    -- and the Riemann sum for f over P is within ε of I
    True) ∧ 
  I = ∫ x in a..b, f x := by sorry