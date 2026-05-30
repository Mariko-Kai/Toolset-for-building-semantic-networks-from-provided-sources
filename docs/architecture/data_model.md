# Каноническая модель данных Mathesis

Единый источник истины — `mathesis/schema.py`. Слой доступа — `mathesis/repo.py`
(+ фасад `mathesis/core.py`). Этот документ описывает схему и маппинг прежних
таксономий.

## Принцип: ось Lean (`def` / `prop`)

Граф знаний строится вокруг ОДНОЙ сущности `entities` с бинарной осью
`type ∈ {def, prop}` — зеркало Lean (определение / утверждение-prop).

**Отдельного вида `axiom` нет.** Аксиома вносится как:
- `def` — если постулирует объект/структуру (примитив);
- `prop` — если постулирует утверждение.

«Постулируется без доказательства» выражается полем `lean_decl='axiom'`
(в Lean: `axiom name : T`) — это деталь *представления*, а не отдельный вид.

## Таблицы

### `entities` (каноническая сущность)
| Колонка | Тип | Назначение |
|---|---|---|
| `entity_id` | TEXT PK | slug, напр. `def-real-analysis-limit` |
| `type` | TEXT, CHECK in (`def`,`prop`) | ось Lean (kind) |
| `title` | TEXT | человекочитаемое имя |
| `path` | TEXT | директория .tex (легаси) |
| `file_path` | TEXT | относительный путь .tex |
| `lean_path` | TEXT | путь валидированного .lean |
| `nl_desc` | TEXT | описание на естественном языке |
| `module` | TEXT | раздел математики |
| `latex` | TEXT | канонический формальный LaTeX |
| `lean_code` | TEXT | сгенерированный Lean 4 |
| `lean_decl` | TEXT | форма декларации Lean (`def\|abbrev\|structure\|class\|instance\|theorem\|lemma\|axiom`) |
| `lean_status` | TEXT, CHECK in (`unvalidated`,`valid`,`sorry`,`failed`) | статус валидации |
| `embedding` | BLOB | вектор для семантического поиска (управляется отдельно) |
| `created_at`, `updated_at` | TEXT | таймстемпы ISO-8601 |

### `alias` — мультиязычные алиасы (O(1) разрешение)
`alias TEXT PK, entity_id → entities ON DELETE CASCADE`.

### `formulation_sources` — провенанс
`id, entity_id → entities, source_book, page_info`. Откуда извлечена сущность.

### `entity_dependency` — типизированный граф зависимостей
`source_id, target_id → entities, role, proof_step, PK(source_id,target_id,role)`.
`role ∈ {uses, generalizes, instance_of, proof_uses, component}` (по умолчанию `uses`).

### `equivalence` — симметричные эквивалентности
`entity_a_id, entity_b_id, proof_id, PK(a,b), CHECK(a<b)` (канонический порядок).

### `entity_fts` — полнотекстовый поиск (FTS5)
Индексирует `title, nl_desc, latex` (`unicode61`). Синхронизируется repo при upsert.

### Индексы
`idx_entities_type`, `idx_entities_module`, `idx_dep_target`, `idx_alias_entity`,
`idx_src_entity`.

## Staging (черновики экстракции; можно очищать без потери канона)
- `formulation_raw_cache` — сырые формулировки из учебников до синтеза.
- `cluster_entity_map` — кластер черновиков → промоутнутая сущность.
- `pending_edges` — очередь нерешённых рёбер (цель ещё не создана).

## Маппинг прежней таксономии → канон

| Прежнее (rich schema) | Канон |
|---|---|
| `object` | `entities` с `type=def` |
| `operation` | `entities` с `type=def` (+ рёбра role=`uses` на аргументы/codomain) |
| `property` | `entities` с `type=prop` |
| `theorem` / `lemma` | `entities` с `type=prop` (lemma: ребро role=`proof_uses`/`component` к родителю) |
| `axiom` | `entities` (`def` или `prop`) с `lean_decl='axiom'` |
| `theorem_object/property/operation` | `entity_dependency` (role=`uses`) |
| `theorem_dependency` | `entity_dependency` (role=`proof_uses`) |
| `object_composition` | `entity_dependency` (role=`component`) |
| `equivalence` | `equivalence` (без изменений) |
| `alias_registry` | `alias` |

## Трассировка
`repo.trace_to_roots(id)` идёт по исходящим рёбрам вглубь; раскрытие обрывается
на аксиоматичных сущностях (`lean_decl='axiom'`) и листьях DAG. Предохранитель от
циклов — глубина ≤ 64; целостность (циклы) проверяет `validator.validate`.

## Версия схемы
`schema_meta.value WHERE key='version'` (текущая: см. `SCHEMA_VERSION` в `schema.py`).
Совместимость: схема — надмножество прежней «плоской» `entities`, поэтому
существующий конвейер продолжает писать в неё без изменений (Этап 2.4 переведёт
его на типизированный staging→promotion).
