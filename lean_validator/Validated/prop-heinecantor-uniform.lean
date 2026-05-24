import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def UniformConvergence (f : ℕ → ℝ → ℝ) (L : ℝ) : Prop :=
  ∀ ε > 0, ∃ N : ℕ, ∀ n ≥ N, ∀ x : ℝ, |f n x - L| < ε

theorem UniformConvergenceAndContinuity (f : ℕ → ℝ → ℝ) (L : ℝ) :
  UniformConvergence f L → Continuous (fun x => f x) := by sorry