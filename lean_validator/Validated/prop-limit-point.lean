import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsLimit (f : ℝ → ℝ) (p L : ℝ) : Prop := 
  ∀ ε > 0, ∃ δ > 0, ∀ x, (x ≠ p ∧ dist x p < δ) → dist (f x) L < ε