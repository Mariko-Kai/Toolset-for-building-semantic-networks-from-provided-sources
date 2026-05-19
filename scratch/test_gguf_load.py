import os
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

print("Torch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())

model_path = "F:/Universe/Projects/Учебник по матанализу/llama/bge-reranker-v2-m3-Q6_K.gguf"
model_dir = os.path.dirname(model_path)
gguf_file = os.path.basename(model_path)

print(f"model_dir: {model_dir}")
print(f"gguf_file: {gguf_file}")

print("Loading tokenizer from BAAI/bge-reranker-v2-m3...")
tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-reranker-v2-m3")
print("Tokenizer loaded successfully.")

print("Loading quantized model from GGUF...")
# In recent versions of transformers, you load it using AutoModelForSequenceClassification.from_pretrained
model = AutoModelForSequenceClassification.from_pretrained(model_dir, gguf_file=gguf_file)
print("Model loaded successfully!")
print("Model type:", type(model))

# Run a test inference
pairs = [["предел функции", "Определение. Число A называется пределом функции f(x) в точке x0..."]]
inputs = tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt")

with torch.no_grad():
    outputs = model(**inputs)
    logits = outputs.logits.squeeze(-1)
    score = torch.sigmoid(logits).item()
    print("Sigmoid probability score:", score)
