from llama_cpp import Llama
import numpy as np

print("Loading GGUF Cross-Encoder in-memory...")
model_path = "F:/Universe/Projects/Учебник по матанализу/llama/bge-reranker-v2-m3-Q6_K.gguf"
# Set ctx length to 2048 or higher
llm = Llama(model_path=model_path, n_ctx=2048, embedding=True, verbose=False)
print("Model loaded successfully!")

# Format a query and document pair
query = "предел функции"
doc = "Определение. Число A называется пределом функции f(x) в точке x0..."

# Tokenize using model's vocabulary
# XLM-RoBERTa / XLM-R format: <s> query </s></s> doc </s>
# BOS token is typically 0, EOS is 2.
query_tokens = llm.tokenize(query.encode("utf-8"), add_bos=True)
doc_tokens = llm.tokenize(doc.encode("utf-8"), add_bos=False)

# Let's inspect the tokens
print(f"BOS token: {llm.token_bos()}")
print(f"EOS token: {llm.token_eos()}")
print(f"Query tokens: {query_tokens[:5]}... (len: {len(query_tokens)})")
print(f"Doc tokens: {doc_tokens[:5]}... (len: {len(doc_tokens)})")

# Combine them: <s> query </s> </s> doc </s>
# If query_tokens already starts with BOS and ends with EOS, and doc_tokens ends with EOS:
tokens = query_tokens + [llm.token_eos()] + doc_tokens
print(f"Combined tokens length: {len(tokens)}")

# Evaluate
print("Evaluating tokens...")
llm.reset()
llm.eval(tokens)

print("Evaluation done!")
print(f"n_tokens evaluated: {len(tokens)}")
# In Sequence Classification / Reranker models, the output is the logit at the first token or last token.
# Let's inspect the logits/scores
scores = llm.eval_logits
print(f"Type of eval_logits: {type(scores)}")
# Convert to numpy array or list to see shape
if hasattr(scores, "shape"):
    print(f"Logits shape: {scores.shape}")
else:
    print(f"Logits length: {len(scores)}")
    # Print the first 10 logits
    print("First 10 logits:", scores[:10])
