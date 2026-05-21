import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def prop_function_discontinuous (f : ℝ → ℝ) (p : ℝ) : Prop :=
  ¬ContinuousAt f p ∧ 
  (¬∃ L, Filter.Tendsto f (nhds p) (nhds L)) ∨ 
  (∃ L, Filter.Tendsto f (nhds p) (nhds L) ∧ L ≠ f p)