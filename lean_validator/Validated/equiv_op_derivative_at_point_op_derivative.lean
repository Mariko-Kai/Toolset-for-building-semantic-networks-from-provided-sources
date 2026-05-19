theorem equiv_op_derivative_at_point_op_derivative (f : ℝ → ℝ) (x : ℝ) (L : ℝ) :
    (op_derivative_at_point f x L) ↔ (op_derivative f x L) := by
  constructor
  · -- Prove the forward direction: op_derivative_at_point f x L → op_derivative f x L
    intro h
    exact h
  · -- Prove the backward direction: op_derivative f x L → op_derivative_at_point f x L
    intro h
    exact h