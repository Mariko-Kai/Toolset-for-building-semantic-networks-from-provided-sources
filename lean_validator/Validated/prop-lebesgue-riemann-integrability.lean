import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

-- Lebesgue criterion for Riemann integrability
def IsRiemannIntegrable (f : ℝ → ℝ) (a b : ℝ) : Prop :=
  BddAbove (f '' Set.Icc a b) ∧ BddBelow (f '' Set.Icc a b) ∧
  MeasureTheory.volume {x | x ∈ Set.Icc a b ∧ ¬ContinuousAt f x} = 0

theorem lebesgue_criterion (f : ℝ → ℝ) (a b : ℝ) : 
  IsRiemannIntegrable f a b ↔ 
  BddAbove (f '' Set.Icc a b) ∧ BddBelow (f '' Set.Icc a b) ∧
  MeasureTheory.volume {x | x ∈ Set.Icc a b ∧ ¬ContinuousAt f x} = 0 := by sorry