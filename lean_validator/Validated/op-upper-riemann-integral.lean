import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

-- Define what it means for a function to be a step function
def IsStepFunction (f : ℝ → ℝ) : Prop := sorry

-- Define the upper Riemann integral
def IsUpperIntegral (f : ℝ → ℝ) (I : ℝ) : Prop :=
  I = ⨅ (g : ℝ → ℝ) (h : IsStepFunction g) (k : ∀ x, f x ≤ g x), 
      ∫ x in (0 : ℝ)..(1 : ℝ), g x

-- Define the upper Riemann integral operation
def op_upper_riemann_integral (f : ℝ → ℝ) : Prop := 
  ∃ I : ℝ, IsUpperIntegral f I