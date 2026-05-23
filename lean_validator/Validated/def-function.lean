import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def Function.IsTotalAndUnique {X Y : Type*} (f : X → Y) : Prop :=
  ∀ x : X, ∃! y : Y, f x = y