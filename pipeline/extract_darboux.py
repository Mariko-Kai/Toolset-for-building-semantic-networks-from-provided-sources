import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from PIL import Image
import time, json
import argparse

PROJECT_ROOT = Path(r'f:\Universe\Projects\Учебник по матанализу')
load_dotenv(PROJECT_ROOT / ".env")

parser = argparse.ArgumentParser(description="Extract mathematical definitions using Gemini Vision")
parser.add_argument("--model", type=str, default="gemini-2.5-pro", choices=["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"], help="Gemini model to use for CV/OCR")
args = parser.parse_args()

system_prompt = """You are a mathematical entity extractor. You are given images of pages from a Russian mathematical analysis textbook (Zorich).

Your task: Extract the FORMAL DEFINITION of the Darboux integral (интеграл Дарбу), including:
1. Lower Darboux sum s(f, P)
2. Upper Darboux sum S(f, P) 
3. Lower Darboux integral I = sup_P s(f, P)
4. Upper Darboux integral I̅ = inf_P S(f, P)
5. The integrability condition: f is Darboux-integrable iff I = I̅

Return a JSON object with fields:
- "status": "SUFFICIENT" or "INSUFFICIENT_SOURCE"
- "definitions": list of objects, each with:
  - "name_ru": name in Russian
  - "name_en": name in English
  - "entity_type": one of "object", "property", "operation", "theorem", "axiom"
  - "entity_id": following the prefix convention (op-, obj-, prop-, thm-)
  - "formula_latex": the PURE MATH formula in LaTeX (no natural language, only math symbols)
  - "page": page number where found
  - "dependencies": list of entity_ids this definition depends on
"""

user_prompt = "Extract the Darboux integral definition from these pages. Include all sub-definitions (partitions, sums, integrals)."

staging_dir = PROJECT_ROOT / "staging" / "zorich-1"
images = sorted(staging_dir.glob("page_*.png"))

client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

img_objects = []
for img_path in images:
    img = Image.open(img_path)
    img_objects.append(img)
    print(f"Loaded {img_path.name} ({img.size})")

print("Sending to Gemini Vision...")
for attempt in range(3):
    try:
        response = client.models.generate_content(
            model=args.model,
            contents=[system_prompt] + img_objects + [user_prompt],
            config={"response_mime_type": "application/json"}
        )
        result = json.loads(response.text)
        
        with open(PROJECT_ROOT / 'pipeline' / 'darboux_vision_result.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\nStatus: {result.get('status')}")
        if 'definitions' in result:
            for d in result['definitions']:
                print(f"  [{d.get('entity_id')}] {d.get('name_ru')} (p.{d.get('page')})")
        break
    except Exception as e:
        print(f"Attempt {attempt+1} failed: {e}")
        time.sleep(5)

print("\nDone. Full result in pipeline/darboux_vision_result.json")
