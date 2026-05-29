import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsEquivalentFunction (f g : ℝ → ℝ) : Prop :=
  ∃ C : ℝ, ∀ x : ℝ, f x = g x + C