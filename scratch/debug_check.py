import sys; sys.path.append('..'); from pipeline.lean_validator import discover_mathlib_signatures; print(discover_mathlib_signatures(['Nat.add', 'Real.cos']))
