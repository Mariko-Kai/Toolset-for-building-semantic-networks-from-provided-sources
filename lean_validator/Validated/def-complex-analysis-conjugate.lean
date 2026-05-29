import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def conjugate (z : ℂ) : ℂ := Complex.re z - Complex.I * Complex.im z