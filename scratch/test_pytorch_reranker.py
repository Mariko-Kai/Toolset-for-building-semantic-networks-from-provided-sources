from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

print("Loading native PyTorch BGE-Reranker-v2-m3 on CPU...")
model_name = "BAAI/bge-reranker-v2-m3"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)
model.eval()

print("Model loaded successfully!")

query = "предел функции"
doc_match = "Определение. Число A называется пределом функции f(x) в точке x0..."
doc_mismatch = "Рецепт пиццы. Возьмите 300 грамм муки, добавьте воду, дрожжи и немного соли. Выпекайте при температуре 220 градусов."

# Formulate pairs
pairs = [[query, doc_match], [query, doc_mismatch]]

print("Running inference...")
inputs = tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt")

with torch.no_grad():
    outputs = model(**inputs)
    logits = outputs.logits.squeeze(-1)
    scores = torch.sigmoid(logits).tolist()

print("\n--- RESULTS ---")
print(f"Match Page Score: {scores[0]:.6f}")
print(f"Mismatch Page Score: {scores[1]:.6f}")
