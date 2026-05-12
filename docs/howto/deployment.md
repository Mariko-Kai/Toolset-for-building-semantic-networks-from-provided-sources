# Развёртывание проекта

Данное руководство описывает процесс установки и запуска Mathesis на вашей локальной машине.

---

## Предварительные требования

| Компонент | Версия | Проверка |
|-----------|--------|----------|
| Python | ≥ 3.10 | `python --version` |
| Git | Любая | `git --version` |
| TeX Live или MikTeX | Свежая | `pdflatex --version` |

---

## Шаги установки

### 1. Клонирование репозитория

```bash
git clone <URL_РЕПОЗИТОРИЯ>
cd "Учебник по матанализу"
```

### 2. Создание виртуального окружения

```bash
python -m venv .venv
```

=== "Windows (PowerShell)"

    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

=== "Linux / macOS"

    ```bash
    source .venv/bin/activate
    ```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

Содержимое `requirements.txt`:
```
fastapi>=0.110
uvicorn>=0.27
jinja2>=3.1
```

!!! note "Зависимости для агента-экстрактора"
    Если вы планируете использовать LLM-агент для извлечения сущностей, также установите:
    ```bash
    pip install google-genai pillow python-dotenv
    ```

### 4. Настройка окружения (для LLM-агента)

Скопируйте шаблон и добавьте свой API-ключ:
```bash
cp .env.template .env
```

Отредактируйте `.env`:
```
GEMINI_API_KEY=ваш_ключ_здесь
```

### 5. Инициализация базы данных

```python
from mathesis import MathesisDB

db = MathesisDB("mathesis_index.db")
db.connect()
db.init_db()
db.close()
```

### 6. Запуск веб-интерфейса

```bash
uvicorn web.app:app --reload
```

Откройте `http://127.0.0.1:8000` в браузере.

---

## Компиляция PDF

Для компиляции `master.tex` в PDF используйте скрипт:

```batch
build.bat
```

Скрипт запускает `pdflatex` дважды (для TOC и перекрёстных ссылок) и проверяет статус выхода (условие: Zero Compile Errors).
