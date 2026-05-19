from llama_cpp import Llama
import llama_cpp.llama_cpp as lc
import numpy as np

print("Loading GGUF Cross-Encoder in generative mode (embedding=False)...")
model_path = "F:/Universe/Projects/Учебник по матанализу/llama/bge-reranker-v2-m3-Q6_K.gguf"
# Use embedding=False
llm = Llama(model_path=model_path, n_ctx=2048, embedding=False, verbose=False)
print("Model loaded successfully!")

query = "предел функции"
doc = "Определение. Число A называется пределом функции f(x) в точке x0..."

query_tokens = llm.tokenize(query.encode("utf-8"), add_bos=True)
doc_tokens = llm.tokenize(doc.encode("utf-8"), add_bos=False)

tokens = query_tokens + [llm.token_eos()] + doc_tokens

llm._batch.reset()
llm._batch.add_sequence(tokens, 0, True)

print("Decoding sequence...")
try:
    # Clear cache and decode
    llm._ctx.kv_cache_clear()
    llm._ctx.decode(llm._batch)
    print("Decode successful!")
    
    # Retrieve logits
    ptr = llm._ctx.get_logits()
    n_vocab = llm.n_vocab()
    n_tokens = len(tokens)
    print(f"n_vocab: {n_vocab}, n_tokens: {n_tokens}")
    
    logits = np.ctypeslib.as_array(ptr, shape=(n_tokens * n_vocab,))
    print(f"Logits total shape: {logits.shape}")
    
    # Let's inspect the logits at the first token (index 0)
    first_token_logits = logits[:n_vocab]
    print("First token logits (first 20):", first_token_logits[:20])
    print("First token logits max:", np.max(first_token_logits), "at index:", np.argmax(first_token_logits))
    print("First token logits min:", np.min(first_token_logits))
except Exception as e:
    print(f"Error during decode: {e}")
