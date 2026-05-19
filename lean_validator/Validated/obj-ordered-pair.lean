import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

-- Definition of ordered pair (structure and equality)
def obj_ordered_pair (p : ℝ × ℝ) : Prop := True

def IsEqualOrderedPair (p q : ℝ × ℝ) : Prop := p.1 = q.1 ∧ p.2 = q.2