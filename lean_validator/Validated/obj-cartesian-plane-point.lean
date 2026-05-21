import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def obj_cartesian_plane_point (p : ℝ × ℝ) : Prop := 
  ∃ (x y : ℝ), p = (x, y)