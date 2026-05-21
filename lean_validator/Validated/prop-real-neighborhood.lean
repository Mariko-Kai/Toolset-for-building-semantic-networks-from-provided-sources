import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsNeighborhood (N : Set ℝ) (p : ℝ) : Prop :=
  ∃ ε > 0, N = {x : ℝ | p - ε < x ∧ x < p + ε}