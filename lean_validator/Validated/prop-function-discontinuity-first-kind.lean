import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsFirstKindDiscontinuity (f : ℝ → ℝ) (a : ℝ) : Prop :=
  ∃ L_minus L_plus : ℝ, 
    Filter.Tendsto f (nhdsWithin a (Set.Iio a)) (nhds L_minus) ∧
    Filter.Tendsto f (nhdsWithin a (Set.Ioi a)) (nhds L_plus) ∧
    (L_minus ≠ f a ∨ L_plus ≠ f a)

theorem FirstKindDiscontinuityProperty (f : ℝ → ℝ) (a : ℝ) : 
  IsFirstKindDiscontinuity f a ↔ 
  ∃ L_minus L_plus : ℝ, 
    Filter.Tendsto f (nhdsWithin a (Set.Iio a)) (nhds L_minus) ∧
    Filter.Tendsto f (nhdsWithin a (Set.Ioi a)) (nhds L_plus) ∧
    (L_minus ≠ f a ∨ L_plus ≠ f a) := by sorry