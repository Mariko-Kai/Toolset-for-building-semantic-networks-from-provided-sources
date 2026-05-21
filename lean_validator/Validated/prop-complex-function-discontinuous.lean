import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat Classical Polynomial

def IsDiscontinuous (f : ℂ → ℂ) (a : ℂ) : Prop := 
  ¬(∃ L : ℂ, Filter.Tendsto f (nhds a) (nhds L) ∧ L = f a)

def prop_complex_function_discontinuous (f : ℂ → ℂ) (a : ℂ) : Prop := 
  IsDiscontinuous f a