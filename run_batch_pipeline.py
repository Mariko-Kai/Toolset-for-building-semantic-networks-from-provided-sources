import subprocess
import sys
import os
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Configuration
LEAN_PROVIDER = "groq"
LEAN_API_KEY = os.environ.get("GROQ_API_KEY", "")
LEAN_MODEL = "openai/gpt-oss-120b"

SYNTH_PROVIDER = "gemini"
SYNTH_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SYNTH_MODEL = "gemini-3.1-flash-lite"

EXTRACT_PROVIDER = "gemini"
EXTRACT_API_KEY = os.environ.get("GEMINI_API_KEY", "")
EXTRACT_MODEL = "gemini-2.5-flash-lite"

QUERIES = [
    "Равномерная сходимость функциональной последовательности",
]

def run_pipeline(query):
    print(f"\n{'='*80}")
    print(f"[*] Processing query: {query}")
    print(f"{'='*80}\n")
    
    cmd = [
        sys.executable, "-u", "pipeline/ollama_wrapper.py", query,
        "--lean-provider", LEAN_PROVIDER,
        "--lean-api-key", LEAN_API_KEY,
        "--lean-model", LEAN_MODEL,
        "--synth-provider", SYNTH_PROVIDER,
        "--synth-api-key", SYNTH_API_KEY,
        "--synth-model", SYNTH_MODEL,
        "--extract-provider", EXTRACT_PROVIDER,
        "--extract-api-key", EXTRACT_API_KEY,
        "--extract-model", EXTRACT_MODEL
    ]
    
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    try:
        # Run and stream output to console
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            encoding='utf-8',
            errors='replace',
            env=env
        )
        
        for line in iter(process.stdout.readline, ''):
            print(line, end='', flush=True)
            
        process.wait()
        if process.returncode != 0:
            print(f"\n[!] Pipeline failed for query '{query}' with return code {process.returncode}")
        else:
            print(f"\n[+] Successfully processed query: {query}")
            
    except Exception as e:
        print(f"\n[!] Error executing pipeline for query '{query}': {e}")

def main():
    # Ensure we are in the project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print(f"[*] Starting batch pipeline for {len(QUERIES)} queries...")
    
    for i, query in enumerate(QUERIES, 1):
        print(f"\n[ {i} / {len(QUERIES)} ]")
        run_pipeline(query)
        
    print("\n[*] Batch processing complete.")

if __name__ == "__main__":
    main()
