import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat Classical Polynomial

def IsBounded (f : ℝ → ℝ) : Prop := ∃ M > 0, ∀ x, |f x| < M