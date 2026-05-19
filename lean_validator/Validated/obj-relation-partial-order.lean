import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

/--
A binary relation R on a type α is a partial order if it is reflexive, antisymmetric, and transitive.
-/
def obj_relation_partial_order {α : Type*} (R : α → α → Prop) : Prop :=
  (∀ x, R x x) ∧ 
  (∀ x y, R x y → R y x → x = y) ∧ 
  (∀ x y z, R x y → R y z → R x z)
