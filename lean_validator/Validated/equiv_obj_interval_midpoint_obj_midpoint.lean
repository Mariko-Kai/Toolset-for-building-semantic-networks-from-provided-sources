theorem equiv_obj_interval_midpoint_obj_midpoint (a b m : ℝ) : (m = (a + b) / 2) ↔ (m = (a + b) / 2) := by
  apply Iff.intro
  · -- Prove the forward direction: if m = (a + b) / 2, then m = (a + b) / 2
    intro h
    exact h
  · -- Prove the backward direction: if m = (a + b) / 2, then m = (a + b) / 2
    intro h
    exact h