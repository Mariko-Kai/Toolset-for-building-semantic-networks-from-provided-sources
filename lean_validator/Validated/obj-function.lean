import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def obj_function (f : ℝ → ℝ) : 
  (∀ x y : ℝ, f x = f y → x = y) := by sorry