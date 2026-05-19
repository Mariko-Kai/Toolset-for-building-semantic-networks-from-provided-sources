import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsLeastUpperBound (B : ℝ) (S : Set ℝ) : Prop :=
  S.Nonempty ∧ 
  (∀ x ∈ S, x ≤ B) ∧ 
  (∀ y : ℝ, y < B → ∃ s ∈ S, s > y)

theorem IsLeastUpperBound.BoundedAbove (S : Set ℝ) (B : ℝ) : 
  IsLeastUpperBound B S → BddAbove S := by sorry