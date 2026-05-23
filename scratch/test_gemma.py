import os
from google import genai
from google.genai import types

api_key = "AIzaSyBBwPDw65A3Ic2AOrL_d7WUpF5RWaql8dA" 
client = genai.Client(api_key=api_key)

try:
    print("Testing with JSON mode and temp=0.1...")
    response = client.models.generate_content(
        model="gemma-4-31b-it",
        contents="Hello, this is a test. Return JSON: {'status': 'ok'}",
        config=types.GenerateContentConfig(
            temperature=0.1, 
            max_output_tokens=1024,
            response_mime_type="application/json"
        )
    )
    print("SUCCESS")
    print(response.text)
except Exception as e:
    print(f"FAILED: {e}")
