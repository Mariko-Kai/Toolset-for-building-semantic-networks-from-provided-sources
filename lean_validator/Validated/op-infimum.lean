import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def op_infimum (L : ℝ) (S : Set ℝ) : Prop :=
  (∀ s ∈ S, L ≤ s) ∧ (∀ y : ℝ, (∀ s ∈ S, y ≤ s) → y ≤ L)