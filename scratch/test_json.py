import json

s = '{"desc": "\\forall"}'
print("Original string:", repr(s))

try:
    print("Parsed without fix:", repr(json.loads(s)["desc"]))
except Exception as e:
    print("Error:", e)

# Fix:
s_fixed = s.replace('\\f', '\\\\f').replace('\\b', '\\\\b').replace('\\r', '\\\\r').replace('\\t', '\\\\t').replace('\\v', '\\\\v')
print("Fixed string:", repr(s_fixed))
try:
    print("Parsed with fix:", repr(json.loads(s_fixed)["desc"]))
except Exception as e:
    print("Error:", e)
