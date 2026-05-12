# Структура проекта

```
Учебник по матанализу/
├── content/                      ← Layer 1: Канонические сущности
│   ├── mathesis.sty              ← Пакет макросов (\entityref, \mForall, ...)
│   ├── master.tex                ← Мастер-документ → PDF
│   ├── TEMPLATE.tex              ← Шаблон новой сущности
│   ├── foundations/              ← Аксиомы, правила вывода (9 файлов)
│   ├── objects/                  ← Математические объекты (95 файлов)
│   ├── properties/               ← Свойства объектов (192 файла)
│   ├── operations/               ← Операции (18 файлов)
│   └── theorems/                 ← Теоремы и леммы (108 файлов)
│
├── sources/                      ← Layer 2: Транскрипции учебников
│   ├── _registry.yaml
│   └── <author>/
│       ├── _meta.yaml
│       └── ch01-topic.tex
│
├── mathesis/                     ← Ядро Python (Модули 3–4)
│   ├── __init__.py               ← Публичные экспорты
│   ├── core.py                   ← MathesisDB — фасад API
│   ├── db.py                     ← DDL, подключение к SQLite
│   ├── models.py                 ← Dataclass-модели сущностей
│   ├── queries.py                ← Все read-запросы (backlinks, DAG, FTS)
│   ├── validator.py              ← Проверки целостности
│   └── exceptions.py             ← Пользовательские исключения
│
├── web/                          ← Модуль 5: Веб-транспорт
│   ├── app.py                    ← FastAPI application
│   ├── static/                   ← CSS, JS
│   └── templates/                ← Jinja2 HTML-шаблоны
│
├── tools/                        ← Утилиты и агенты
│   ├── agent/
│   │   └── agent.py              ← LLM-агент для извлечения сущностей
│   ├── pdftoimages/
│   │   └── pdf_to_images.py      ← Конвертация PDF → изображения
│   ├── link_content.py           ← Парсер .tex → SQLite
│   ├── apply_entity_names.py     ← Применение имён к сущностям
│   ├── inject_titles.py          ← Инъекция заголовков
│   ├── fix_math_mode.py          ← Исправление математического режима
│   └── reset_function_links.py   ← Сброс ссылок
│
├── Books/                        ← Исходные учебники (PDF)
├── docs/                         ← Эта документация (MkDocs)
├── mkdocs.yml                    ← Конфигурация MkDocs
├── requirements.txt              ← Python-зависимости
├── build.bat                     ← Скрипт компиляции master.tex
├── .env                          ← Секреты (GEMINI_API_KEY)
└── .env.template                 ← Шаблон переменных окружения
```

---

## Ключевые директории

### `content/` — Математические сущности

Каждый файл содержит **ровно одну** математическую сущность. Файлы именуются по конвенции `Human Name [id].tex`. Внутри используются макросы из `mathesis.sty`.

На данный момент в базе:

| Категория | Количество файлов |
|-----------|------------------|
| `foundations/` | 9 |
| `objects/` | 95 |
| `properties/` | 192 |
| `operations/` | 18 |
| `theorems/` | 108 |

### `mathesis/` — Python-ядро

Реализует паттерн **фасад**: класс `MathesisDB` в `core.py` оборачивает внутренние модули (`db`, `queries`, `validator`) и предоставляет единый публичный API.

### `tools/` — Утилиты

Содержит скрипты для полуавтоматической обработки контента: от извлечения через LLM до парсинга и интеграции в БД.

### `web/` — Веб-интерфейс

FastAPI-приложение с рендерингом формул через KaTeX. Шаблоны используют Jinja2.
