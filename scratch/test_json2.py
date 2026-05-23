import json

s = r'{"desc": "\forall a \in A, \frac{1}{2}, \beta, \nu, \n (newline)"}'
print("Original:", repr(s))

latex_conflicts = ['forall', 'frac', 'beta', 'rightarrow', 'Rightarrow', 'rho', 'tau', 'theta', 'text', 'nu', 'nabla', 'big', 'bar']
for conflict in latex_conflicts:
    s = s.replace('\\' + conflict, '\\\\' + conflict)

print("Fixed:", repr(s))
print("Parsed:", repr(json.loads(s)["desc"]))
