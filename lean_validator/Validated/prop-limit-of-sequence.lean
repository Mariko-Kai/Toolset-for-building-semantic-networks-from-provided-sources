import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def HasLimit (f : ℝ → ℝ) (L : ℝ) : Prop :=
  ∀ ε > 0, ∃ N : ℝ, N > 0 ∧ ∀ n : ℕ, n > N → |f n - L| < ε