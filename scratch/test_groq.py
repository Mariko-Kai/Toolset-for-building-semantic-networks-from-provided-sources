import os
import openai
client = openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.environ.get("GROQ_API_KEY", ""))

print("Testing Groq Llama 3.3 70B...")
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Hello, how are you?"}],
    temperature=0.0,
    max_tokens=1024,
)
print(f"Response: '{response.choices[0].message.content.strip()}'")
