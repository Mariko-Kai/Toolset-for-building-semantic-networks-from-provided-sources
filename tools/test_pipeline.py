import sys
from unittest.mock import patch
from pipeline.enrichment_coordinator import main

def test_run():
    test_args = ["enrichment_coordinator.py", "определение интеграла Римана", "--model", "llama3.1:8b"]
    with patch.object(sys, 'argv', test_args):
        main()

if __name__ == "__main__":
    test_run()
