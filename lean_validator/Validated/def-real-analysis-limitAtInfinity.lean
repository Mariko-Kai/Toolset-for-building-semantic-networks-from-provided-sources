import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsLimitAtPlusInfinity (f : ℝ → ℝ) : Prop :=
  ∀ ε > 0, ∃ M : ℝ, ∀ x : ℝ, |x| > M → f x > ε