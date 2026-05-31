import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

theorem prop_taylor_series_expandability_criterion (f : ℝ → ℝ) (a : ℝ) 
  (hf_cont : ContinuousAt f a)
  (hf_smooth : ContDiff ℝ ⊤ f)
  (hf_conv : ∃ r > 0, ∀ x ∈ Set.Ioo (a - r) (a + r), Summable (fun n => (deriv^[n] f a) / n! * (x - a)^n)) :
  ∃ r > 0, ∀ x ∈ Set.Ioo (a - r) (a + r), 
    f x = ∑' n, (deriv^[n] f a) / n! * (x - a)^n := by sorry