# Добавление нового шаблона LaTeX

Это руководство описывает, как добавить новую математическую сущность в систему.

---

## Формат файла

Каждый `.tex` файл содержит ровно **одну** сущность. Имя файла следует конвенции:

```
Human Name [id].tex
```

Примеры:
```
Bounded [prop-bounded].tex
Derivative [op-derivative].tex
Bolzano-Weierstrass [thm-bolzano-weierstrass].tex
```

---

## Шаблон сущности

Используйте `content/TEMPLATE.tex` как основу:

```latex
% entity-id: <TYPE-PREFIX>-<SEMANTIC-NAME>
% entity-type: <object|property|operation|theorem|axiom>
% defined-in: <книга>, p. <номер_страницы>

\section{<НАЗВАНИЕ НА РУССКОМ>}

\begin{<TYPE>}[<Название>]
\label{entity:<ID>}

% 1. ОБЪЯВЛЕНИЕ ТИПОВ (Strict Typing Block)

% 2. ТЕЛО ОПРЕДЕЛЕНИЯ (Definitional Body)

\end{<TYPE>}
```

---

## Правила идентификаторов

| Тип сущности | Префикс ID | Пример |
|--------------|-----------|--------|
| Аксиома | `axm-` | `axm-zfc-choice` |
| Объект | `obj-` | `obj-sequence` |
| Свойство | `prop-` | `prop-bounded` |
| Операция | `op-` | `op-derivative` |
| Теорема | `thm-` | `thm-bolzano-weierstrass` |
| Лемма | `lemma-` | `lemma-bw-bisection` |

---

## Размещение файла

| Тип | Директория |
|-----|-----------|
| Аксиомы, правила вывода | `content/foundations/` |
| Объекты | `content/objects/` |
| Свойства | `content/properties/` |
| Операции | `content/operations/` |
| Теоремы и леммы | `content/theorems/` |

---

## Подключение в master.tex

После создания файла добавьте его в `content/master.tex`:

```latex
\input{objects/Subsequence [obj-subsequence]}
```

!!! warning "Важно"
    Директории внутри категорий — **плоские** (без вложенных папок). Все файлы одного типа лежат в одной директории.

---

## Использование `\semantic macro`

Для ссылок на другие сущности используйте **только** макрос из `mathesis.sty`:

```latex
\semantic macro{obj-set}{X}
```

Это создаёт гиперссылку в PDF и позволяет автоматически извлечь граф зависимостей.
