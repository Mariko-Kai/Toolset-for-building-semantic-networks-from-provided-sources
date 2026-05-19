import os
import openai

client = openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.environ.get("GROQ_API_KEY", ""))

prompt = r"""Synthesize a strict formal DEFINITION from these sources:
[zorich]: derivative of a function at a point.

CRITICAL: DO NOT add any notes, remarks, text, or English words outside or inside the block. ONLY the formal mathematical formula.
Generate \begin{object}[Name] ... \end{object} (or property/operation)."""

print("Testing Groq LaTeX synthesis...")
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.0,
    max_tokens=1024,
)
resp = response.choices[0].message.content.strip()
print(f"Response ({len(resp)} chars): '{resp}'")
