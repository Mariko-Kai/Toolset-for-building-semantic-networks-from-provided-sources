import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsLimit (x : ℕ → ℝ) (A : ℝ) : Prop :=
  ∀ ε > 0, ∃ N : ℕ, ∀ n : ℕ, n > N → |x n - A| < ε

theorem limit_converges (x : ℕ → ℝ) (A : ℝ) : 
  IsLimit x A ↔ Filter.Tendsto x Filter.atTop (nhds A) := by sorry