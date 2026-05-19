import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsEqual (z₁ z₂ : ℂ) : Prop := z₁.re = z₂.re ∧ z₁.im = z₂.im

theorem equality_of_complex_numbers : 
  ∀ z₁ z₂ : ℂ, IsEqual z₁ z₂ ↔ z₁.re = z₂.re ∧ z₁.im = z₂.im := by sorry