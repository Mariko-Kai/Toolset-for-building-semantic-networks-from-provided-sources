import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem prop_abels_power_series (a : ℕ → ℝ) (x : ℝ) : 
  Summable (fun n => a n * x^n) ↔ 
  (∃ r > 0, ∀ n, |a n| ≤ M * r^n) := by sorry