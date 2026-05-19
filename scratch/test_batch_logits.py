from llama_cpp import Llama
import numpy as np
import ctypes

print("Loading GGUF Cross-Encoder in-memory...")
model_path = "F:/Universe/Projects/Учебник по матанализу/llama/bge-reranker-v2-m3-Q6_K.gguf"
llm = Llama(model_path=model_path, n_ctx=2048, embedding=True, verbose=False)
print("Model loaded successfully!")

query = "предел функции"
doc = "Определение. Число A называется пределом функции f(x) в точке x0..."

query_tokens = llm.tokenize(query.encode("utf-8"), add_bos=True)
doc_tokens = llm.tokenize(doc.encode("utf-8"), add_bos=False)

# Combined sequence
tokens = query_tokens + [llm.token_eos()] + doc_tokens
print(f"Tokens: {tokens}")

# Reset batch and add sequence
llm._batch.reset()
# add_sequence(tokens, seq_id, logits_all)
llm._batch.add_sequence(tokens, 0, True)

print("Decoding via low-level _ctx...")
llm._ctx.kv_cache_clear()
llm._ctx.decode(llm._batch)
print("Decode completed successfully!")

# Retrieve logits
# llama.cpp's llama_get_logits returns the logits of all tokens (if logits_all is True)
ptr = llm._ctx.get_logits()
n_vocab = llm.n_vocab()
n_tokens = len(tokens)
print(f"n_vocab: {n_vocab}, n_tokens: {n_tokens}")

# Convert ctypes float pointer to numpy array
logits = np.ctypeslib.as_array(ptr, shape=(n_tokens * n_vocab,))
print(f"Logits total shape: {logits.shape}")

# Let's inspect the logits at the first token (index 0)
first_token_logits = logits[:n_vocab]
print("First token logits sample:", first_token_logits[:20])
print("First token logits max:", np.max(first_token_logits), "at index:", np.argmax(first_token_logits))
print("First token logits min:", np.min(first_token_logits))
