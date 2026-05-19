import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsNeighborhood (N : Set ℝ) (p : ℝ) : Prop := 
  ∃ ε > 0, N = Set.Ioo (p - ε) (p + ε)

theorem neighborhood_equivalence (N : Set ℝ) (p : ℝ) : 
  IsNeighborhood N p ↔ IsOpen N ∧ p ∈ N ∧ ∀ x ∈ N, ∃ ε > 0, |x - p| < ε := by sorry