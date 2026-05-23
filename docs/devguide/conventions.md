# Правила оформления кода

## Python

### Стиль кода

- Следуйте [PEP 8](https://peps.python.org/pep-0008/).
- Максимальная длина строки: **88 символов** (по умолчанию для `black`).
- Используйте **type hints** для всех публичных функций и методов.
- Все модели — `dataclass`-ы (без ORM).

### Docstrings

Все публичные функции и классы должны иметь docstring:

```python
def get_object(conn: sqlite3.Connection, id: str) -> models.Object:
    """Fetch an Object by its entity ID.

    Args:
        conn: Active SQLite connection.
        id: Semantic entity ID (e.g. 'obj-sequence').

    Returns:
        The Object dataclass instance.

    Raises:
        EntityNotFoundError: If no object with the given ID exists.
    """
```

### Исключения

Используйте кастомные исключения из `mathesis.exceptions`:

| Исключение | Назначение |
|-----------|-----------|
| `EntityNotFoundError` | Сущность с данным ID не найдена |
| `DuplicateEntityError` | Попытка создать сущность с существующим ID |
| `ValidationError` | Ошибка валидации данных |
| `ParseError` | Невозможно распарсить `.tex` файл |

---

## LaTeX

### Канонические макросы

Все определения обязаны использовать макросы из `mathesis.sty`:

| Назначение | Макрос | ❌ Неправильно |
|-----------|--------|----------------|
| Кванторы | `\Forall{x}`, `\mExists{x}` | `\forall x` |
| Импликация | `\mImplies` | `\Rightarrow` |
| Определение | `\mDefIff` | `:=` |
| Множества чисел | `\mReal`, `\mNatural` | `\mathbb{R}` |
| Пустое множество | `\mEmpty` | `\emptyset` |
| Конструктор множества | `\mSet{...}` | `\{...\}` |

### Правила оформления определений

1. **Одна концепция на определение** — без конъюнкций.
2. **Только display math** — никаких inline формул внутри определений.
3. **Без естественного языка** — `\text{}` только для стандартных терминов.
4. **Блок типизации + тело** — обязательное разделение на Strict Typing Block и Definitional Body.

### Именование файлов

```
Human Name [prefix-semantic-id].tex
```

Примеры:
```
Set [obj-set].tex
Bounded [prop-bounded].tex
Bolzano-Weierstrass [thm-bolzano-weierstrass].tex
```

---

## Git

### Что НЕ коммитить

В `.gitignore` должны быть:
```
.venv/
*.aux
*.log
*.out
*.toc
mathesis_index.db
site/
.env
```

### Сообщения коммитов

Используйте префиксы:
```
feat: добавлен obj-metric-space
fix: исправлена ссылка на prop-bounded
docs: обновлена страница архитектуры
refactor: вынесен код валидации
```
