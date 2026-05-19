import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem obj_open_interval (a b : ℝ) (h : a < b) : 
  {x : ℝ | a < x ∧ x < b} = Set.Ioo a b := by sorry