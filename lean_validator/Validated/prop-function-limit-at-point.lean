import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def prop_function_limit_at_point (f : ℝ → ℝ) (p A : ℝ) : Prop :=
  ∀ ε > 0, ∃ δ > 0, ∀ x, 0 < abs (x - p) ∧ abs (x - p) < δ → abs (f x - A) < ε