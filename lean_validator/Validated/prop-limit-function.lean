import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsLimit (f : ℝ → ℝ) (a L : ℝ) : Prop :=
  ∀ ε > 0, ∃ δ > 0, ∀ x : ℝ, (0 < abs (x - a) ∧ abs (x - a) < δ) → abs (f x - L) < ε

theorem IsLimit_iff : 
  ∀ f : ℝ → ℝ, ∀ a L : ℝ, IsLimit f a L ↔ Filter.Tendsto f (nhds a) (nhds L) := by sorry