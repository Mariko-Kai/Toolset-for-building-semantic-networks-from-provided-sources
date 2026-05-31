from pipeline.canonical_synthesizer import warn_natural_language, validate_macros_exist

def test_warn_natural_language_detects_text():
    # Test natural language inside \begin{proposition} is flagged
    latex_bad = r"""
% entity-id: prop-test
% entity-type: prop
\begin{proposition}[Test]
\[
\TerForall a \left( \Series{\sum a_n} \text{ converges} \right)
\]
\end{proposition}
"""
    errors = warn_natural_language(latex_bad)
    assert len(errors) > 0
    assert "ОШИБКА" in errors[0]

def test_warn_natural_language_detects_raw_words():
    # Test natural language raw words (like "converges uniformly") inside \begin{proposition}
    latex_bad = r"""
\begin{proposition}[Test]
\[
f \text{ converges uniformly on } \ClosedInterval{0, 1}
\]
\end{proposition}
"""
    errors = warn_natural_language(latex_bad)
    assert len(errors) > 0
    assert "ОШИБКА" in errors[0]

def test_warn_natural_language_ignores_proof():
    # Test natural language inside \begin{proof} is NOT flagged
    latex_ok = r"""
\begin{proposition}[Test]
\[
\TerForall x \quad f(x) > 0
\]
\end{proposition}
\begin{proof}[RU]
Здесь разрешен русский текст и \text{ converges }.
\end{proof}
"""
    errors = warn_natural_language(latex_ok)
    assert len(errors) == 0

def test_warn_natural_language_accepts_clean_math():
    # Test completely clean math proposition is NOT flagged
    latex_ok = r"""
\begin{proposition}[Test]
\[
\TerForall a \colon \NaturalNumbers \TermTo \RealNumbers \left( s(m)(x) = \sum_{n=0}^{m} a_n x^n \right)
\]
\end{proposition}
"""
    errors = warn_natural_language(latex_ok)
    assert len(errors) == 0

def test_validate_macros_exist_detects_fake_macros():
    # Test fake/hallucinated macros are flagged
    latex_bad = r"""
% entity-id: prop-test
% entity-type: prop
\begin{proposition}[Test]
\[
\TerImplication \TerConjunction \Series{\sum a_n}
\]
\end{proposition}
"""
    # \TerImplication and \TerConjunction are misspelled/fake (should be \TermImplication and \TermConjunction)
    errors = validate_macros_exist(latex_bad)
    assert len(errors) == 2
    assert any("TerImplication" in e for e in errors)
    assert any("TerConjunction" in e for e in errors)

def test_validate_macros_exist_allows_valid():
    # Test valid standard and custom macros are allowed
    latex_ok = r"""
% entity-id: prop-test
% entity-type: prop
% macro: \TestMacro
\begin{proposition}[Test]
\[
\TermImplication \TermConjunction \Series{\sum_{n=0}^{\infty} a_n} \TestMacro
\]
\end{proposition}
"""
    errors = validate_macros_exist(latex_ok)
    assert len(errors) == 0
