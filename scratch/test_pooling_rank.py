from llama_cpp import Llama
import llama_cpp.llama_cpp as lc
import numpy as np

print("Loading GGUF Cross-Encoder with pooling_type=4 (RANK)...")
model_path = "F:/Universe/Projects/Учебник по матанализу/llama/bge-reranker-v2-m3-Q6_K.gguf"

# Load model with embedding=True and pooling_type=4 (which is LLAMA_POOLING_TYPE_RANK)
llm = Llama(
    model_path=model_path, 
    n_ctx=2048, 
    embedding=True, 
    pooling_type=4, # 4 = LLAMA_POOLING_TYPE_RANK
    verbose=False
)
print("Model loaded successfully!")

def get_rerank_score(query, doc):
    query_tokens = llm.tokenize(query.encode("utf-8"), add_bos=True)
    doc_tokens = llm.tokenize(doc.encode("utf-8"), add_bos=False)
    # Combine tokens: <s> query </s> </s> doc </s>
    tokens = query_tokens + [llm.token_eos()] + doc_tokens
    
    llm._batch.reset()
    llm._batch.add_sequence(tokens, 0, True)
    
    llm._ctx.kv_cache_clear()
    llm._ctx.decode(llm._batch)
    
    # Retrieve embeddings
    emb_ptr = lc.llama_get_embeddings(llm._ctx.ctx)
    n_embd = llm.n_embd()
    emb_arr = np.ctypeslib.as_array(emb_ptr, shape=(n_embd,))
    return emb_arr.copy()

# Case 1: Perfect Match
query = "предел функции"
doc_match = "Определение. Число A называется пределом функции f(x) в точке x0..."
emb_match = get_rerank_score(query, doc_match)

# Case 2: Complete Mismatch
doc_mismatch = "Рецепт пиццы. Возьмите 300 грамм муки, добавьте воду, дрожжи и немного соли. Выпекайте при температуре 220 градусов."
emb_mismatch = get_rerank_score(query, doc_mismatch)

print("\n--- RESULTS WITH pooling_type=4 ---")
print("Embedding dimension:", len(emb_match))
print("Match embedding (first 10 elements):", emb_match[:10])
print("Mismatch embedding (first 10 elements):", emb_mismatch[:10])

print("\nValue at index 0 (which should be the score if ranking pooling is used):")
print(f"Match: {emb_match[0]:.6f}")
print(f"Mismatch: {emb_mismatch[0]:.6f}")
