import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsDiscontinuity (f : ℝ → ℝ) (a : ℝ) : Prop :=
  ∃ ε > 0, ∀ δ > 0, ∃ x, |x - a| < δ ∧ |f x - f a| > ε

theorem IsDiscontinuity_def (f : ℝ → ℝ) (a : ℝ) : 
  IsDiscontinuity f a ↔ 
  ¬ContinuousAt f a := by sorry