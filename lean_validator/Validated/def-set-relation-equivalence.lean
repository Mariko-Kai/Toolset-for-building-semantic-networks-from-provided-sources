import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem def_set_relation_equivalence (A : Type*) (R : Set (A × A)) :
  (∀ x : A, (x, x) ∈ R) ∧ 
  (∀ x y : A, (x, y) ∈ R → (y, x) ∈ R) ∧ 
  (∀ x y z : A, ((x, y) ∈ R ∧ (y, z) ∈ R) → (x, z) ∈ R) →
  Equivalence (fun x y : A => (x, y) ∈ R) := by sorry