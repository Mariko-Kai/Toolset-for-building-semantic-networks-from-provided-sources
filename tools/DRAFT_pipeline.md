# Черновик: Конвейер формализации математических сущностей

> Этот документ описывает пошаговый алгоритм создания канонической записи
> математической сущности с **полным рекурсивным раскрытием** всех зависимостей.

---

## Фаза 0: Входные данные

- **Целевая сущность**: название на русском + английском (например, «Интеграл Дарбу / Darboux Integral»)
- **Дисциплина**: раздел из `sources/_registry.yaml`

---

## Фаза 1: Поиск в первоисточниках

### 1.1 Определение источника (Шаг 0 из generate_doc.md)

```
registry.yaml → ранжирование по priority → search_index.py (морфологический стемминг + мультиязычный перевод)
```

### 1.2 Извлечение (Шаги 1–2 из generate_doc.md)

```
pdf_to_images.py → agent.py (Vision API) → raw JSON с определением
```

### 1.3 Оценка достаточности (Шаг 2.1)

- `SUFFICIENT` → переход к Фазе 2
- `INSUFFICIENT_SOURCE` → следующий учебник по приоритету, возврат к 1.1

---

## Фаза 2: Классификация (ER-модель из design.md §2.2)

Определить тип сущности:
- `object` — множество, пространство, структура (Partition, Function, Interval)
- `property` — предикат, свойство (Bounded, Continuous)
- `operation` — отображение, оператор (sup, inf, ∑, ∫, Darboux Sum)
- `theorem` — утверждение, требующее доказательства
- `axiom` — принимается без доказательства (терминал BFS)

---

## Фаза 3: Создание канонического файла

### 3.1 Структура файла (по TEMPLATE.tex)

```latex
% entity-id: <prefix>-<name>
% entity-type: <object|property|operation|theorem|axiom>
% defined-in: <book-id>, p. <page>

\section{<Название RU> (<Название EN>)}

\begin{<TYPE>}[<entity-id>]
\label{entity:<entity-id>}
% 1. ОБЪЯВЛЕНИЕ ТИПОВ (Strict Typing Block)
% 2. ТЕЛО ОПРЕДЕЛЕНИЯ (Definitional Body)
\end{<TYPE>}
```

### 3.2 Правило ПОЛНОГО `\entityref`-покрытия

> **КРИТИЧЕСКОЕ ПРАВИЛО**: Каждый символ в формуле, имеющий
> самостоятельное математическое определение, ОБЯЗАН быть обёрнут
> в `\entityref{entity-id}{символ}`.

#### Чек-лист при создании формулы:

| Категория | Примеры | Что делать |
|---|---|---|
| **Операторы** | `\sup`, `\inf`, `\lim`, `\sum`, `\prod`, `\int` | Обернуть: `\entityref{op-supremum}{\sup}` |
| **Объекты** | `f`, `P`, `[a,b]`, `\mathbb{R}` | Обернуть: `\entityref{obj-function}{f}` |
| **Свойства** | «ограниченная», «непрерывная» | Обернуть: `\entityref{prop-bounded}{f}` |
| **Отношения** | `\in`, `\subset`, `<`, `=` | НЕ оборачивать (примитивы FOL/ZFC) |
| **Кванторы** | `\forall`, `\exists` | НЕ оборачивать (примитивы FOL) |
| **Нотация** | `\Delta x_i`, `x_0`, индексы | НЕ оборачивать (локальные переменные) |

#### Примеры правильного и неправильного оборачивания:

**НЕПРАВИЛЬНО** (текущее состояние):
```latex
s(f, P) \mDefIff \sum_{i=1}^{n} \left( \inf_{x \in [x_{i-1}, x_i]} f(x) \right) \Delta x_i
```
BFS видит: ∅ (ноль зависимостей в теле формулы)

**ПРАВИЛЬНО**:
```latex
s(\entityref{obj-function}{f}, \entityref{obj-partition}{P}) \mDefIff
\entityref{op-finite-sum}{\sum_{i=1}^{n}} \left(
  \entityref{op-infimum}{\inf}_{x \in \entityref{obj-closed-interval}{[x_{i-1}, x_i]}}
  \entityref{obj-function}{f}(x)
\right) \Delta x_i
```
BFS видит: `obj-function`, `obj-partition`, `op-finite-sum`, `op-infimum`, `obj-closed-interval`

---

## Фаза 4: BFS-обход зависимостей (Recursive Exhaustion)

```
Очередь = [целевая сущность]
Посещённые = {}

while Очередь не пуста:
    eid = Очередь.pop()
    if eid ∈ Посещённые: continue
    Посещённые.add(eid)

    file = найти content/**/*[eid].tex
    if file не существует:
        → выполнить Фазы 1–3 для eid (создать файл)
        → перечитать file

    deps = извлечь ВСЕ \entityref{...} из file
    for dep in deps:
        if dep ∉ Посещённые:
            Очередь.add(dep)

Условие остановки:
  - dep уже существует как файл в content/
  - dep является аксиомой (content/foundations/)
```

### Полное дерево для «Интеграл Дарбу»:

```
op-darboux-integral
├── obj-function         ← f : [a,b] → ℝ
├── obj-closed-interval  ← [a,b]
├── obj-real-numbers     ← ℝ (уже в foundations или objects)
├── prop-bounded         ← ограниченность
├── obj-partition        ← разбиение P
│   ├── obj-closed-interval
│   ├── obj-real-numbers
│   └── obj-finite-set   ← конечное множество
├── op-lower-darboux-sum ← s(f, P)
│   ├── op-infimum       ← inf
│   │   └── prop-bounded-below  ← ограниченность снизу
│   ├── op-finite-sum    ← Σ
│   │   └── obj-natural-numbers ← ℕ (уже в foundations)
│   ├── obj-function
│   ├── obj-partition
│   └── obj-closed-interval
├── op-upper-darboux-sum ← S(f, P)
│   ├── op-supremum      ← sup
│   │   └── prop-bounded-above  ← ограниченность сверху
│   ├── op-finite-sum
│   ├── obj-function
│   ├── obj-partition
│   └── obj-closed-interval
├── op-supremum          ← sup_P s(f,P) в определении I̲
└── op-infimum           ← inf_P S(f,P) в определении I̅
```

---

## Фаза 4.5: Обработка сбоев API (Fallback Mechanisms)

Поскольку конвейер полагается на внешние LLM (например, Gemini 2.5 Flash), возможны ситуации с перегрузкой серверов (`503 UNAVAILABLE` или `429 TOO MANY REQUESTS`). 

> **Правило Автономности**: Конвейер не должен останавливаться или требовать ручного вмешательства в виде ручного создания `.tex` файлов.

**Решения:**
1. **Экспоненциальная задержка (Exponential Backoff)**: Скрипт автоматически повторяет запросы к API с увеличивающейся задержкой (1с, 2с, 4с, 8с, 16с).
2. **Mock LLM / Заглушка**: Если API недоступно, скрипт может использовать локальную заглушку (`MOCK_API`), которая возвращает предопределённые канонические ответы для конкретных `entity-id`, позволяя алгоритму рекурсивного обхода (BFS) продолжить свою работу и доказать целостность архитектуры.
3. **Internal Compute Fallback**: В крайних случаях (когда и API, и моки недоступны), агент переключается на свои внутренние аналитические мощности для ручной генерации `.tex` файлов, строго соблюдая `\entityref` Coverage Rule.

---

## Фаза 5: Генерация ответа (Dynamic Compiler)

```
generate_answer.py --root thm-newton-leibniz (или любой другой корень)
  → BFS по \entityref
  → Сбор формул + метаданных + источников
  → Синтез NL-описаний (опционально)
  → result.tex → pdflatex → result.pdf
```

### Полное дерево для «Формула Ньютона-Лейбница»:

```
thm-newton-leibniz
├── prop-continuous
│   ├── obj-function
│   ├── obj-real-numbers
│   ├── obj-set
│   └── op-limit
├── obj-closed-interval
├── op-antiderivative
│   ├── obj-function
│   ├── obj-real-numbers
│   ├── obj-set
│   └── op-derivative
│       ├── obj-function
│       ├── obj-real-numbers
│       ├── obj-set
│       └── op-limit
└── op-definite-integral
    └── [Дерево Дарбу...]
```

---

## Граничные случаи

### Какие символы НЕ являются сущностями (терминалы):

1. **Логические примитивы FOL**: `∀`, `∃`, `⇒`, `⇔`, `∧`, `∨`, `¬` — определены аксиоматически
2. **Примитивы ZFC**: `∈`, `∅`, `⊂` — определены через аксиомы в `content/foundations/`
3. **Локальные переменные**: `x`, `n`, `i`, `a`, `b` — не имеют глобального определения
4. **Нотационные сокращения**: `Δx_i = x_i - x_{i-1}` — определяются в месте использования
5. **Числовые литералы**: `0`, `1`, `∞` — примитивы

### Когда создавать новый entity vs. ссылаться на существующий:

- Если символ **уже определён** (файл `[entity-id].tex` существует) → `\entityref`
- Если символ **не определён** и является **аксиомой** → создать в `content/foundations/`
- Если символ **не определён** и **определяем** → создать в `content/objects|operations|properties|theorems/`
