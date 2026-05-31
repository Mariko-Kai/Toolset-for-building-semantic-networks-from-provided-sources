import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem prop_riemann_integrability_continuous_function (f : ℝ → ℝ) (a b : ℝ) 
  (h : ContinuousOn f (Set.Icc a b)) : 
  IntervalIntegrable f volume a b := by sorry