import re
text = r'''\begin{object}
\textbf{Описание:}
foo
\textbf{Аксиоматика:}
bar
\end{object}'''
print("Original:")
print(repr(text))
m = re.search(r'\\textbf\{Описание:\}\s*.*?(?=\\begin\{(?:object|axiom|theorem|operation|property)\}|\\textbf\{(?!Описание)\}|\\section|$)', text, flags=re.DOTALL)
print("Match:")
print(repr(m.group(0)) if m else None)
