import sys
from unittest.mock import patch
from pipeline.ollama_wrapper import main

def test_run():
    test_args = ["ollama_wrapper.py", "определение интеграла Римана", "--model", "llama3.1:8b"]
    with patch.object(sys, 'argv', test_args):
        main()

if __name__ == "__main__":
    test_run()
