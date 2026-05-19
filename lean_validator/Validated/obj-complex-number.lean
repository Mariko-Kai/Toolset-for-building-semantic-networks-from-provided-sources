import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def obj_complex_number : 
  ∀ z : ℂ, ∃ (a b : ℝ), z = Complex.mk a b ∧ Complex.re z = a ∧ Complex.im z = b := by sorry