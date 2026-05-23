# Отладка LaTeX-ошибок

Проект Mathesis генерирует LaTeX-код программно. Ошибки, возникающие на стыке Python и LaTeX, требуют специфического подхода к отладке.

---

## Типичные ошибки

### 1. Неопределённая команда (`Undefined control sequence`)

```
! Undefined control sequence.
l.42 \Forall
```

**Причина:** Файл не подключает `mathesis.sty` или макрос отсутствует в пакете.

**Решение:** Убедитесь, что `master.tex` содержит `\usepackage{mathesis}` и нужный макрос определён в `content/mathesis.sty`.

---

### 2. Отсутствующий файл (`File not found`)

```
! LaTeX Error: File `objects/Missing Entity [obj-missing].tex' not found.
```

**Причина:** `master.tex` ссылается на файл, который не был создан агентом или был удалён.

**Решение:** Проверьте наличие файла в директории. Либо создайте stub, либо удалите строку `\input{}` из `master.tex`.

---

### 3. Битая перекрёстная ссылка (`Undefined label`)

```
LaTeX Warning: Reference `entity:obj-topological-space' on page 12 undefined.
```

**Причина:** `\entityref` ссылается на сущность, файл которой не содержит соответствующий `\label`.

**Решение:**

1. Убедитесь, что файл целевой сущности существует и содержит `\label{entity:<ID>}`.
2. Убедитесь, что целевой файл подключён в `master.tex`.
3. Запустите `build.bat` дважды — ссылки разрешаются на втором проходе.

---

### 4. Ошибки кодировки

**Причина:** Python генерирует LaTeX с кодировкой, отличной от ожидаемой `pdflatex`.

**Решение:** Убедитесь, что все `.tex` файлы сохранены в UTF-8. В `master.tex` должно быть:
```latex
\usepackage[utf8]{inputenc}
```

---

## Инструменты отладки

### Пошаговая компиляция

Вместо запуска `build.bat` используйте интерактивный режим:
```bash
cd content
pdflatex -interaction=scrollmode master.tex
```

### Валидация базы данных

После загрузки данных запустите валидацию для поиска битых ссылок:

```python
from mathesis import MathesisDB

db = MathesisDB("mathesis_index.db")
db.connect()
report = db.validate()

if not report.is_valid:
    for ref in report.broken_refs:
        print(f"  ❌ {ref}")
    for cycle in report.cycles:
        print(f"  🔄 Цикл: {' → '.join(cycle)}")
    for orphan in report.orphan_lemmas:
        print(f"  👻 {orphan}")

db.close()
```
