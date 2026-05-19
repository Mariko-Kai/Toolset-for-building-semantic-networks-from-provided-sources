import os
import sys

sys.path.append(r"f:\Universe\Projects\Учебник по матанализу")

from pipeline.export_to_lean import query_groq
from pipeline.canonical_synthesizer import build_synthesis_prompt
import openai

client = openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.environ.get("GROQ_API_KEY", ""))

formulations = [{"text": "derivative of a function at a point. ...", "source": "zorich"}]
sources = ["zorich"]

prompt = build_synthesis_prompt("01880a18", formulations, sources, "definition")

print(f"Testing Groq LaTeX synthesis with full prompt... ({len(prompt)} chars)")
resp = query_groq(prompt, client=client, model="llama-3.3-70b-versatile")
print(f"Response ({len(resp)} chars): '{resp}'")
