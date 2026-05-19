theorem equiv_obj_predicate_obj_term : (obj_predicate : Type) = (obj_term : Type) := by
  have h : (obj_predicate : Type) = (obj_term : Type) := by
    -- Use the `ext` tactic to prove the equality of types by proving the equality of their elements.
    apply Eq.symm
    apply Eq.symm
    -- Use the `aesop` tactic to automatically solve the goal.
    aesop
  -- The result follows directly from the established equality.
  exact h