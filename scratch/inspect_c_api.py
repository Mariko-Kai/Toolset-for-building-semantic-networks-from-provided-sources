import llama_cpp.llama_cpp as lc
print("Searching for 'rerank' in llama_cpp ctypes bindings:")
for attr in dir(lc):
    if "rerank" in attr.lower():
        print(f"  Found: {attr}")
