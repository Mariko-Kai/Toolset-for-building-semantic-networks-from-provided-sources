import json
clean_ans = r'{"test": "\notin"}'
print('Before:', repr(clean_ans))
latex_conflicts = {"\\f": "\\\\f", "\\b": "\\\\b", "\\v": "\\\\v", 
                   "\\r": "\\\\r", "\\t": "\\\\t", "\\n": "\\\\n"}
for k, v in latex_conflicts.items():
    clean_ans = clean_ans.replace(k, v)
print('After:', repr(clean_ans))
print('Loaded:', repr(json.loads(clean_ans)['test']))
