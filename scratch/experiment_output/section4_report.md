# Раздел 4. Результаты эксперимента

## 4.1 Инвентаризация узлов семантической сети

| Тип сущности | Количество | Доля |
|---|---|---|
| axiom | 14 | 39% |
| object | 15 | 42% |
| operation | 2 | 6% |
| **ИТОГО** | **36** | **100%** |

- Обнаружено незакрытых зависимостей (dangling `\entityref`): **5**
- Отсутствующие сущности: `obj-finite-set`, `obj-ordered-pair`, `op-abs-abstract`, `op-infimum`, `prop-partial-order`

## 4.2 Синтез из кэша формулировок (LLM)

| # | Кластер | Источник | Время (с) | Статус | entity-id | Размер |
|---|---|---|---|---|---|---|
| 1 | `65465ddf` | spivak | 330.9 | degraded | `PARSE_FAIL` | 0 |
| 2 | `73c24663` | zorich, zorich | 260.4 | ok | `thm-riemann-integral-definition` | 878 |
| 3 | `f0089935` | spivak | 436.4 | ok | `thm-riemann-integral` | 1211 |
| 4 | `a87b518e` | apostol, apostol | 450.0 | ok | `op-riemann-integral` | 1521 |
| 5 | `a7ec9df3` | apostol | 348.9 | degraded | `PARSE_FAIL` | 0 |

**Результат:** 3/5 кластеров успешно синтезированы.
Среднее время синтеза: **365.3с** на кластер.

## 4.3 Lean-трансляция и валидация

| Метрика | Значение |
|---|---|
| Всего сущностей | 39 |
| Нет транслируемого контента | 13 |
| Прошли синтаксический анализ | 0 |
| Не прошли синтаксический анализ | 0 |
| Прошли Lean 4 type-check | 11 |
| Не прошли Lean 4 type-check | 14 |

### Детализация по сущностям

| entity-id | Тип | Источник | Lean-статус | Ошибки |
|---|---|---|---|---|
| `axm-zfc-choice` | axiom | existing | lean_fail | unexpected token '\'; expected ')' or term |
| `axm-zfc-extensionality` | axiom | existing | lean_fail | Failed to infer type of binder `A`; unexpected token ','; expected command |
| `axm-zfc-infinity` | axiom | existing | lean_fail | unexpected token '\'; expected ')', '_', identifie |
| `axm-zfc-pairing` | axiom | existing | lean_fail | Failed to infer type of binder `A`; unexpected token ','; expected command |
| `axm-zfc-power-set` | axiom | existing | lean_fail | typeclass instance problem is stuck
  Membership ? |
| `axm-zfc-regularity` | axiom | existing | lean_fail | typeclass instance problem is stuck
  Membership ( |
| `axm-zfc-replacement` | axiom | existing | lean_fail | unexpected token '!'; expected '(', '_' or identif |
| `axm-zfc-specification` | axiom | existing | lean_fail | unexpected token '\'; expected term |
| `axm-zfc-union` | axiom | existing | lean_fail | typeclass instance problem is stuck
  Membership ( |
| `axm-completeness` | axiom | existing | lean_fail | unexpected token '\'; expected ')', '_', identifie |
| `axm-fol-5` | axiom | existing | lean_fail | unexpected token '\'; expected ')', '_', identifie |
| `axm-fol-generalization` | axiom | existing | lean_fail | unexpected token '\'; expected term |
| `axm-fol-modus-ponens` | axiom | existing | lean_fail | unexpected token '\'; expected term |
| `axm-fol-4` | axiom | existing | lean_fail | unexpected token '\'; expected ')', '_', identifie |
| `obj-cartesian-product` | object | existing | no_content |  |
| `obj-closed-interval` | object | existing | lean_pass |  |
| `obj-function` | object | existing | lean_pass |  |
| `obj-natural-numbers` | object | existing | lean_pass |  |
| `obj-closed-interval` | object | existing | lean_pass |  |
| `obj-riemann-integral` | object | existing | no_content |  |
| `obj-partition` | object | existing | lean_pass |  |
| `obj-predicate` | object | existing | lean_pass |  |
| `obj-real-numbers` | object | existing | lean_pass |  |
| `obj-riemann-class` | object | existing | lean_pass |  |
| `obj-sequence` | object | existing | lean_pass |  |
| `obj-set` | object | existing | no_content |  |
| `obj-subset` | object | existing | no_content |  |
| `obj-term` | object | existing | lean_pass |  |
| `obj-wff-fol` | object | existing | lean_pass |  |
| `obj-riemann-integral` | operation | existing | no_content |  |
| `op-riemann-integral` | operation | existing | no_content |  |
| `term-log-conn` | terminal | existing | no_content |  |
| `term-in` | terminal | existing | no_content |  |
| `term-set` | terminal | existing | no_content |  |
| `term-subset` | terminal | existing | lean_pass |  |
| `term-forall` | terminal | existing | no_content |  |
| `thm-riemann-integral-definition` | theorem | synthesized | no_content |  |
| `thm-riemann-integral` | theorem | synthesized | no_content |  |
| `op-riemann-integral` | operation | synthesized | no_content |  |

**Доля успешной Lean-валидации:** 11/26 (42%)

## 4.4 Сводная статистика

| Показатель | Значение |
|---|---|
| Узлов в `content/` (до эксперимента) | 36 |
| Синтезировано новых узлов | 3 |
| Общее количество узлов (после) | 39 |
| Валидация Lean (type-check) | 11 из 26 |
| Незакрытые зависимости | 5 |
