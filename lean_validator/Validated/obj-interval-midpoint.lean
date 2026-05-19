import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def obj_interval_midpoint (a b m : ℝ) : Prop := m = (a + b) / 2