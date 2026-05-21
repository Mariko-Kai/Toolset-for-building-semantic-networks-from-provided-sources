import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

def IsVertexR (P₂ P₃ Q R : EuclideanSpace ℝ (Fin n)) : Prop := 
  R = P₃ + Q - P₂

theorem parallelogram_vertex_r (P₂ P₃ Q R : EuclideanSpace ℝ (Fin n)) : 
  IsVertexR P₂ P₃ Q R ↔ R = P₃ + Q - P₂ := by sorry