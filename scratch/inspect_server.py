import llama_cpp.server.app as server_app
settings = server_app.Settings(model="F:/Universe/Projects/Учебник по матанализу/llama/bge-reranker-v2-m3-Q6_K.gguf", embedding=True)
app = server_app.create_app(settings=settings)
print("Exposed routes:")
for route in app.routes:
    methods = getattr(route, "methods", None)
    print(f"  {route.path} - Methods: {methods}")
