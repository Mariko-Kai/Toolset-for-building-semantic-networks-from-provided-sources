import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

-- Uniform convergence on a set S for functions f_n and f
def def_uniform_convergence (S : Set α) (f_n : ℕ → (α → ℝ)) (f : α → ℝ) : Prop :=
  ∀ ε > 0, ∃ N : ℕ, ∀ n > N, ∀ x ∈ S, |f_n n x - f x| < ε