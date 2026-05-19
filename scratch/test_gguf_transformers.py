try:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    print("Transformers version:")
    import transformers
    print(transformers.__version__)
    
    # Try loading the GGUF model
    print("Attempting to load GGUF model via transformers...")
    model_path = "F:/Universe/Projects/Учебник по матанализу/llama/bge-reranker-v2-m3-Q6_K.gguf"
    
    # AutoTokenizer might need the original Hugging Face model ID for configuration
    tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-reranker-v2-m3")
    print("Tokenizer loaded successfully.")
    
    # Try loading the sequence classification model from GGUF
    model = AutoModelForSequenceClassification.from_pretrained(model_path, gguf_file=model_path)
    print("Model loaded successfully!")
except Exception as e:
    print(f"Error loading: {e}")
