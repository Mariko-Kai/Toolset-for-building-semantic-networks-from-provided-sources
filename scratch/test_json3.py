import json
import re

response = r'{"desc": "\forall a \in A, \frac{1}{2}, \beta, \nu, \n (newline)"}'

# Fix LaTeX commands that conflict with JSON escapes
latex_conflicts = ['forall', 'frac', 'beta', 'rightarrow', 'Rightarrow', 'rho', 'tau', 'theta', 'text', 'nu', 'nabla', 'big', 'bar']
for conflict in latex_conflicts:
    response = response.replace(f'\\{conflict}', f'\\\\{conflict}')

try:
    res = json.loads(response)
except json.JSONDecodeError:
    response = re.sub(r'\\(?![/"\\bfnrt])', r'\\\\', response)
    res = json.loads(response)

print("Parsed:", repr(res["desc"]))
