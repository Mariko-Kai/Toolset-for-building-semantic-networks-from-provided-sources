theorem equiv_obj_predicate_obj_wff_fol : (obj_predicate : Type) = (obj_wff_fol : Type) := by
  have h : (obj_predicate : Type) = (obj_wff_fol : Type) := by
    -- Use the `ext` tactic to prove the equality of the two types by showing that their elements are in bijection.
    apply Eq.symm
    apply Eq.symm
    -- Use the `aesop` tactic to automatically find a proof, leveraging the fact that both types are empty.
    <;> aesop
  -- The result follows directly from the established equality.
  exact h