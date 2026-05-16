import os
import google.generativeai as genai

# Use the API key provided in the user's command
api_key = "AIzaSyBBwPDw65A3Ic2AOrL_d7WUpF5RWaql8dA" 
genai.configure(api_key=api_key)

print("Available Models:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
