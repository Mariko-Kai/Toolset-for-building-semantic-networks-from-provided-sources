import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

def test_extraction(image_path: Path):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not set.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    system_prompt = """
    Вы - эксперт-математик. Ваша задача - извлечь каноническую запись (определение или теорему) для запрошенного термина по предоставленному изображению страницы учебника.
    
    ТРЕБОВАНИЯ К КАНОНИЧЕСКОЙ ЗАПИСИ:
    1. Она должна быть строго на математическом языке (кванторы, логические связки).
    2. В ней НЕ ДОЛЖНЫ быть пропущены используемые неявно сущности (например, если говорится о функции, нужно явно указать кванторы для её области определения и значений).
    3. Не должно быть пропущено никаких логических шагов.
    4. Все используемые математические термины и объекты должны быть обернуты в макрос \entityref{id}{text}.
    5. Запись должна соответствовать формату LaTeX (внутри блока ```latex).
    
    Если предоставленной страницы (или источника) НЕ ХВАТАЕТ для формирования полной, математически строгой канонической записи без пропуска неявных сущностей, вы обязаны вернуть строку:
    INSUFFICIENT_SOURCE
    
    Никаких извинений или обходных путей. Если не хватает данных - просто верните INSUFFICIENT_SOURCE.
    """
    
    user_prompt = "Найди и сформулируй каноническое определение термина 'аналитическая функция'. Помни о правиле INSUFFICIENT_SOURCE, если на этой странице нет достаточно строгой информации для исчерпывающего определения."
    
    img = Image.open(image_path)
    
    print(f"Sending request to Gemini Vision for {image_path.name}...")
    import time
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[system_prompt, img, user_prompt]
            )
            print("----- RESPONSE -----")
            print(response.text)
            print("--------------------")
            break
        except Exception as e:
            print(f"Attempt {attempt+1} Error: {e}")
            if "429" in str(e):
                print("Rate limited, sleeping for 20 seconds...")
                time.sleep(20)
            else:
                break

if __name__ == "__main__":
    img_path = PROJECT_ROOT / "pipeline" / "pdftoimages" / "staging" / "zorich-1" / "page_504.png"
    if img_path.exists():
        test_extraction(img_path)
    else:
        print(f"Image not found at {img_path}")
