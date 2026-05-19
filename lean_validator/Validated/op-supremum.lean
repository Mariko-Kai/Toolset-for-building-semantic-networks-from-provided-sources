import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def op_supremum (s : ℝ) (X : Set ℝ) : Prop :=
  (∀ x ∈ X, x ≤ s) ∧ (∀ s' < s, ∃ x ∈ X, s' < x)