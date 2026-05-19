def op_derivative_at_point (f : ℝ → ℝ) (x : ℝ) (L : ℝ) : Prop :=
  ∀ ε > 0, ∃ δ > 0, ∀ h : ℝ, 0 < |h| ∧ |h| < δ → |(f (x + h) - f x) / h - L| < ε