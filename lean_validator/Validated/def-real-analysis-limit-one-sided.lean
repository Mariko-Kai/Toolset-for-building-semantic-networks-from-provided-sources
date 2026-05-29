import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsLeftLimit (f : ℝ → ℝ) (x₀ : ℝ) (L : ℝ) : Prop :=
  ∀ ε > 0, ∃ δ > 0, ∀ x, x₀ - δ < x ∧ x < x₀ → |f x - L| < ε

theorem def_real_analysis_limit_one_sided (f : ℝ → ℝ) (x₀ : ℝ) (L : ℝ) :
  IsLeftLimit f x₀ L ↔ Filter.Tendsto f (nhdsWithin x₀ (Set.Iio x₀)) (nhds L) := by sorry