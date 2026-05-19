import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def prop_infimum (S : Set ℝ) (L : ℝ) : Prop := 
  (∀ s ∈ S, L ≤ s) ∧ ¬(∃ L' : ℝ, L' > L ∧ ∀ s ∈ S, L' ≤ s)