from llama_cpp import Llama
import llama_cpp.llama_cpp as lc
import numpy as np

print("Loading GGUF Cross-Encoder in-memory...")
model_path = "F:/Universe/Projects/Учебник по матанализу/llama/bge-reranker-v2-m3-Q6_K.gguf"
llm = Llama(model_path=model_path, n_ctx=2048, embedding=True, verbose=False)
print("Model loaded successfully!")

query = "предел функции"
doc = "Определение. Число A называется пределом функции f(x) в точке x0..."

query_tokens = llm.tokenize(query.encode("utf-8"), add_bos=True)
doc_tokens = llm.tokenize(doc.encode("utf-8"), add_bos=False)

tokens = query_tokens + [llm.token_eos()] + doc_tokens

llm._batch.reset()
llm._batch.add_sequence(tokens, 0, True)

llm._ctx.kv_cache_clear()
llm._ctx.decode(llm._batch)

# Inspect standard embeddings
emb_ptr = lc.llama_get_embeddings(llm._ctx.ctx)
if emb_ptr:
    emb_arr = np.ctypeslib.as_array(emb_ptr, shape=(100,))
    print("llama_get_embeddings (first 100):", emb_arr[:20])
    print("Non-zero embeddings:", np.count_nonzero(emb_arr))
else:
    print("llama_get_embeddings returned NULL")

# Inspect seq embeddings (for seq 0)
seq_emb_ptr = lc.llama_get_embeddings_seq(llm._ctx.ctx, 0)
if seq_emb_ptr:
    seq_emb_arr = np.ctypeslib.as_array(seq_emb_ptr, shape=(100,))
    print("llama_get_embeddings_seq (first 100):", seq_emb_arr[:20])
    print("Non-zero seq embeddings:", np.count_nonzero(seq_emb_arr))
else:
    print("llama_get_embeddings_seq returned NULL")
