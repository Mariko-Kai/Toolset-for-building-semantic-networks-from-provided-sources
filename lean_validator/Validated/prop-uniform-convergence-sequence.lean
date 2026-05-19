import Mathlib.Data.Real.Basic
import Mathlib.Topology.Basic

/--
The property of uniform convergence for a sequence of functions f_n to a function f on a set A.
-/
def UniformConvergence {A : Set ℝ} (f_n : ℕ → A → ℝ) (f : A → ℝ) : Prop :=
  ∀ ε > 0, ∃ N : ℕ, ∀ n ≥ N, ∀ x : A, |f_n n x - f x| < ε

theorem prop_uniform_convergence_sequence 
  (A : Set ℝ) 
  (f_n : ℕ → A → ℝ) 
  (f : A → ℝ) : 
  UniformConvergence f_n f ↔ ∀ ε > 0, ∃ N : ℕ, ∀ n ≥ N, ∀ x : A, |f_n n x - f x| < ε := by
  rfl