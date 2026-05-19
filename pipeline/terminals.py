"""
Terminal Primitives — symbols that are leaf nodes in the Mathesis DAG.
These MUST NOT be wrapped in \entityref by the LLM.
They MUST NOT generate entity_dependency edges.
"""

# FOL (First-Order Logic) terminals
FOL_TERMINALS = {
    r'\forall', r'\exists', r'\exists!', r'\Rightarrow', r'\Leftrightarrow',
    r'\land', r'\lor', r'\lnot', r'\vdash',
}

# ZFC set-theoretic terminals  
ZFC_TERMINALS = {
    r'\in', r'\emptyset', r'\subset', r'\subseteq',
    r'\cup', r'\cap', r'\setminus',
}

# Equality/ordering — syntactic, not semantic
RELATIONAL_TERMINALS = {
    '=', '<', '>', r'\leq', r'\geq', r'\neq',
}

# Numeric literals & notation
NOTATION_TERMINALS = {
    '0', '1', r'\infty', r'\Delta', r'\varepsilon', r'\delta',
}

# Canonical macro equivalents (already in mathesis.sty)
MACRO_TERMINALS = {
    r'\mForall', r'\mExists', r'\mImplies', r'\mIff',
    r'\mAnd', r'\mOr', r'\mNot', r'\mTurnstile',
    r'\mIn', r'\mSubset', r'\mSubseteq',
    r'\mEmpty', r'\mDefIff', r'\mQED', r'\mDefinedAs', r'\mathrm',
    r'\to', r'\mTo', r'\colon',
    r'\hypertarget', r'\hyperlink',
}

ALL_TERMINALS = FOL_TERMINALS | ZFC_TERMINALS | RELATIONAL_TERMINALS | NOTATION_TERMINALS | MACRO_TERMINALS
