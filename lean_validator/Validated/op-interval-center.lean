import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def op_interval_center (c a b : ℝ) : Prop := c = (a + b) / 2