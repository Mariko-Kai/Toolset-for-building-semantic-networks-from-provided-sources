def IsRemovableDiscontinuity (f : ℝ → ℝ) (a : ℝ) : Prop := 
  ∃ L, Filter.Tendsto f (nhds a) (nhds L) ∧ L ≠ f a