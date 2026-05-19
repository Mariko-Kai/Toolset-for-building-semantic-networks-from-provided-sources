from gguf import GGUFReader

model_path = "F:/Universe/Projects/Учебник по матанализу/llama/bge-reranker-v2-m3-Q6_K.gguf"
reader = GGUFReader(model_path)

print("Tensors in GGUF related to classification head or output:")
for i, tensor in enumerate(reader.tensors):
    name = tensor.name
    # Search for cls or classifier, but exclude attn_output
    if any(k in name.lower() for k in ["cls", "classifier"]) and "attn" not in name.lower():
        print(f"  Tensor {i}: {name} (shape: {tensor.shape}, type: {tensor.tensor_type})")
