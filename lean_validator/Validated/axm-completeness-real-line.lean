import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem axm_completeness_real_line (L : Type*) [LinearOrder L] [Nonempty L] :
  ¬∃ (A B : Set L), 
    (A.Nonempty) ∧ 
    (B.Nonempty) ∧ 
    (A ∪ B = Set.univ) ∧ 
    (A ∩ B = ∅) ∧ 
    (∀ a ∈ A, ∀ b ∈ B, a < b) ∧ 
    (¬∃ p : L, p ∈ A ∨ p ∈ B) := by sorry