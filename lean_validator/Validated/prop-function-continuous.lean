import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsContinuous (m n : ℕ) (f : EuclideanSpace ℝ (Fin m) → EuclideanSpace ℝ (Fin n)) : Prop :=
  ∀ (U : Set (EuclideanSpace ℝ (Fin n))), IsOpen U → IsOpen (f ⁻¹' U)

theorem ContinuousFunction_prop (m n : ℕ) (f : EuclideanSpace ℝ (Fin m) → EuclideanSpace ℝ (Fin n)) : 
  IsContinuous m n f ↔ Continuous f := by sorry