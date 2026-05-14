import Mathlib

-- axm-zfc-choice
axiom axm_zfc_choice : ∀ \mathcal{F, } ( ∀ A, B, ( A \in \mathcal{F} \land B \in \mathcal{F} \land A \neq B → \lnot ∃ x, (x \in A \land x \in B) ) \land \lnot(\\varnothing \in \mathcal{F}) ) → ∃ C, ∀ A, ( A \in \mathcal{F} → ∃ ! x, (x \in A \land x \in C) )

-- axm-zfc-extensionality
axiom axm_zfc_extensionality : ∀ A, B, (A = B) ↔ (∀ x, x \in A ↔ x \in B)

-- axm-zfc-infinity
axiom axm_zfc_infinity : ∃ I, ( \\varnothing \in I \;\land\; ∀ x, ( x \in I → ∃ y, (y \in I \land ∀ z, (z \in y ↔ z \in x \lor z = x)) ) )

-- axm-zfc-pairing
axiom axm_zfc_pairing : ∀ A, B, ∃ C, ∀ x, ( x \in C ↔ (x = A \lor x = B) )

-- axm-zfc-power-set
axiom axm_zfc_power_set : ∀ X, ∃ P, ∀ A, (A \in P ↔ A \subset X)

-- axm-zfc-regularity
axiom axm_zfc_regularity : ∀ S, ( (∃ y, y \in S) → ∃ x, ( x \in S \land \lnot ∃ z, (z \in S \land z \in x) ) )

-- axm-zfc-replacement
axiom axm_zfc_replacement : ( ∀ x, ∃ ! y, \, \phi(x, y) ) → ∀ X, ∃ Y, ∀ y, ( y \in Y ↔ ∃ x, ( x \in X \land \phi(x, y) ) )

-- axm-zfc-specification
axiom axm_zfc_specification : ∀ X, ∃ Y, ∀ z, ( z \in Y ↔ (z \in X \land \phi(z)) )

-- axm-zfc-union
axiom axm_zfc_union : ∀ \mathcal{F, } ∃ U, ∀ x, ( x \in U ↔ ∃ A, (A \in \mathcal{F} \land x \in A) )

-- ax-completeness
axiom ax_completeness : (\mForall x \in X ∧ \mForall y \in Y \colon x \le y) → (\mExists c \in \mReal \mForall x \in X, \mForall y \in Y \colon x \le c \le y)

-- ax-fol-5
axiom ax_fol_5 : (\mForall x (\mathcal{B} \to \mathcal{C})) \to (\mathcal{B} \to (\mForall x \mathcal{C}))

-- ax-fol-4
axiom ax_fol_4 : (\mForall x \mathcal{B}(x)) \to \mathcal{B}(t)

-- obj-closed-interval
def obj_closed_interval : Type := \{ x \in \mathbb{R} \mid a \le x \le b \}

-- obj-finite-set
axiom obj_finite_set : Type

-- obj-function
axiom obj_function : Type

-- obj-natural-numbers
axiom obj_natural_numbers : Type

-- obj-partition
def obj_partition : Type := \{x_0, x_1, \ldots, x_n\} \subset [a, b] \colon a = x_0 < x_1 < \cdots < x_n = b

-- obj-predicate
def obj_predicate : Type := (\mathcal{A}^n --- предикатный символ) ∧ (\mForall i \in \{1,\ldots,n\} \colon t_i \in \mathcal{T})

-- obj-real-numbers
axiom obj_real_numbers : Type

-- obj-riemann-class
def obj_riemann_class : Type := \{ f \mid \mExists \int_a^b f(x) dx \}

-- obj-sequence
def obj_sequence : Type := f \colon \mathbb{N} \to X

-- obj-set
axiom obj_set : Type

-- obj-term
def obj_term : Type := (t \in \mathcal{V}) ∨ (t \in \mathcal{C}) ∨ (\mExists f^n ∧ \mExists t_1, \ldots, t_n \in \mathcal{T} \colon t = f^n(t_1, \ldots, t_n))

-- obj-wff-fol
def obj_wff_fol : Type := (At(\mathcal{A})) ∨ (\mExists \mathcal{B} \in \mathcal{F} \colon \mathcal{A} = \neg \mathcal{B}) ∨ (\mExists \mathcal{B}, \mathcal{C} \in \mathcal{F} \colon \mathcal{A} = \mathcal{B} \to \mathcal{C}) ∨ (\mExists x \in \mathcal{V}, \mExists \mathcal{B} \in \mathcal{F} \colon \mathcal{A} = \mForall x \mathcal{B})

-- op-abs
theorem op_abs : |x| := sorry

-- op-antiderivative
axiom op_antiderivative : F = Prim(f) ↔ \mForall x \in I \colon F'(x) = f(x)

-- op-darboux-integral
theorem op_darboux_integral : \underline{I} := sorry

-- op-definite-integral
theorem op_definite_integral : \int_a^b f(x) dx := sorry

-- op-derivative
theorem op_derivative : f'(x_0) := sorry

-- op-finite-sum
theorem op_finite_sum : \sum_{i=1}^n a_i := sorry

-- rule-generalization
axiom rule_generalization : \frac{\mathcal{A}}{\mForall x \mathcal{A}}

-- op-implication
theorem op_implication : \mathcal{A} \to \mathcal{B} := sorry

-- op-infimum
axiom op_infimum : m = \inf A ↔ \mForall x \in A \colon x \ge m ∧ \mForall \varepsilon > 0 \mExists x_{\varepsilon} \in A \colon x_{\varepsilon} < m + \varepsilon

-- op-limit
axiom op_limit : \lim_{x \to x_0} f(x) = A ↔ \mForall \varepsilon > 0 \mExists \delta > 0 \mForall x \in X \colon (0 < |x - x_0| < \delta → |f(x) - A| < \varepsilon)

-- op-lower-darboux-sum
theorem op_lower_darboux_sum : s(f, P) := sorry

-- rule-modus-ponens
axiom rule_modus_ponens : \frac{\mathcal{A}, \mathcal{A} \to \mathcal{B}}{\mathcal{B}}

-- op-negation
theorem op_negation : \neg \mathcal{A} := sorry

-- op-riemann-integral
theorem op_riemann_integral : I = \int_a^b f(x) dx := sorry

-- op-supremum
axiom op_supremum : M = \sup A ↔ \mForall x \in A \colon x \le M ∧ \mForall \varepsilon > 0 \mExists x_{\varepsilon} \in A \colon x_{\varepsilon} > M - \varepsilon

-- op-universal-quantifier
theorem op_universal_quantifier : \mForall x \mathcal{A} := sorry

-- op-upper-darboux-sum
theorem op_upper_darboux_sum : S(f, P) := sorry

-- prop-bounded
def prop_bounded : Prop := ограничена(f) ↔ \mExists M > 0 \colon \mForall x \in X → |f(x)| \le M

-- prop-continuous
def prop_continuous : Prop := непрерывна(f, x_0) ↔ \lim_{x \to x_0} f(x) = f(x_0)

-- thm-newton-leibniz
axiom thm_newton_leibniz : \int_a^b f(x) dx = F(b) - F(a)

-- thm-quantifier-dist
axiom thm_quantifier_dist : MP \colon (Ax_5 ∧ Ax_4) → ( \mForall x (\mathcal{B}(x) \to \mathcal{C}(x)) \to (\mForall x \mathcal{B}(x) \to \mForall x \mathcal{C}(x)) )

