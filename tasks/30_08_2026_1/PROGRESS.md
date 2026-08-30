# PROGRESS — Telegram-бот анализа эмоций и состояния

**Plan:** [PLAN.md](PLAN.md)
**Updated:** 30.08.2026

## Status

**Задача выполнена.** Все 10 этапов закрыты, все пункты Definition of done
отмечены. Suite зелёный: **224 passed**, покрытие `src/moodbot` — **97 %**.

## Environment

| | |
|---|---|
| Python | 3.12.10 — `C:\Users\elman\AppData\Local\Programs\Python\Python312\python.exe` |
| Virtualenv | `.venv/` |
| Install | `.venv/Scripts/python.exe -m pip install -e ".[dev]"` |
| Run tests | `.venv/Scripts/python.exe -m pytest -q` |
| Coverage | `.venv/Scripts/python.exe -m pytest --cov=src/moodbot --cov-report=term-missing -q` |
| Check config | `.venv/Scripts/python.exe -m moodbot --check` |
| Run the app | `.venv/Scripts/python.exe -m moodbot` |
| Required env vars | `TELEGRAM_BOT_TOKEN` (обяз.), `ANTHROPIC_API_KEY` (опц.), `MOODBOT_DB_PATH`, `MOODBOT_MODEL`, `MOODBOT_TIMEOUT_SECONDS` (опц.) |

`python` на PATH — заглушка Microsoft Store; интерпретатор вызывать только по
полному пути. Для читаемого вывода кириллицы — `PYTHONIOENCODING=utf-8`.

Разрешённые версии: `aiogram 3.31.0`, `anthropic 1.2.0`, `pydantic 2.13.5`,
`pytest 9.1.1`, `pytest-asyncio 1.4.0`.

## Executed steps

### 0 — подготовка окружения — ✅

Python отсутствовал (только алиасы Microsoft Store). Установлен через winget по
согласованию с пользователем.

```
winget install --id Python.Python.3.12 --silent
Successfully installed  [exit 0]
Python 3.12.10 / pip 25.0.1
```

### 0.1 — скиллы и агент — ✅

- `.claude/skills/task-plan/` — планирование и итеративное исполнение
- `.claude/skills/python-tdd/` — конвенции кода и слои тестов
- `.claude/agents/python-dev.md` — агент, выполняющий один шаг плана test-first

### 1.1 / 1.2 — каркас и зависимости — ✅

```
aiogram 3.31.0 / anthropic 1.2.0 / moodbot 0.1.0
pytest -q  →  no tests ran in 0.01s
```

### 2.1 / 2.2 — модели и конфигурация — ✅

```
pytest tests/unit -q
31 passed in 0.06s
```

### 3.1 / 3.2 — распознавание кризиса и короткое замыкание — ✅

```
pytest tests/unit -q
88 passed in 0.18s
```

Главная гарантия зафиксирована тестами `test_crisis_text_never_reaches_the_analyzer`
и `test_gate_runs_before_the_analyzer_even_when_it_would_raise`.

### 4.1 — резервный анализатор — ✅

Первый прогон нашёл настоящий баг: стем `тревог` не покрывает «тревожно»
(там `тревож`) — три теста упали.

```
pytest tests/unit/test_fallback_analyzer.py -q
3 failed, 15 passed

# после правки стемов на "трево"
pytest tests/unit -q
106 passed in 0.19s
```

### 5.1 / 5.2 — хранилище — ✅

```
pytest tests/integration -q
20 passed in 1.72s
```

### 6.1 / 6.2 — анализатор на Claude — ✅

Сборка сначала упала: `ModuleNotFoundError: No module named 'conftest'` —
`tests/mock/` является пакетом, поэтому `conftest.py` не импортируется как модуль
верхнего уровня. Фейки вынесены в общий `tests/fakes.py`.

```
pytest tests/mock -q
25 passed in 0.14s

pytest -q
151 passed in 2.38s
```

### 7.1 — форматирование — ✅

```
pytest tests/unit/test_formatting.py -q
23 passed in 0.11s
```

### 8.1 / 8.2 — хендлеры и ветки ошибок — ✅

```
pytest tests/mock/test_handlers.py tests/mock/test_handlers_errors.py -q
29 passed in 0.17s
```

### 9.1 / 9.2 / 9.3 — сборка, сквозной тест, README — ✅

```
pytest tests/integration/test_end_to_end.py -q
13 passed in 8.13s

TELEGRAM_BOT_TOKEN=... python -m moodbot --check
Configuration OK
  model            : claude-opus-5
  analyzer         : rule-based
  database         : ...\moodbot_check.sqlite3
  request timeout  : 45.0s
  note             : ANTHROPIC_API_KEY is not set, replies will use the rule-based analyzer
exit=0
```

### 10.1 — приёмка — ✅

Первый прогон с покрытием дал 96 %, но `bot/telegram.py` был покрыт лишь на 67 %:
адаптер aiogram не проверялся ничем. Добавлен `tests/mock/test_telegram_adapter.py`
— он же поймал бы потерю чанков при отправке.

```
pytest --cov=src/moodbot --cov-report=term-missing -q
TOTAL  710 stmts  16 miss  136 branch  9 brpart  97%
224 passed in 13.93s
```

Непокрытыми остались только пути, поднимающие сеть: `bot/app.run`,
`build_bot` и ветка long polling в `__main__`.

## Next steps

Задача закрыта. Возможные продолжения — отдельными задачами:

1. Экспорт записей из SQLite в лист «Данные» книги `эмоции.xlsx` (сознательно вынесен из объёма).
2. Голосовые сообщения через транскрибацию.
3. Еженедельная сводка динамики по накопленным записям.
4. Расширение кризисных паттернов и их проверка на реальных формулировках.

## Open questions / blockers

- Бот не запускался против реального Telegram: `TELEGRAM_BOT_TOKEN` есть только
  у пользователя. Проверено всё, кроме собственно long polling.
- Реальный вызов Anthropic API также не выполнялся — контракт проверен на
  фейковом клиенте по схеме из документации SDK.

## Decisions

- **SQLite отдельно от `эмоции.xlsx`** — выбор пользователя; экспорт вне объёма.
- **Python поставлен через winget** — с явного согласия; иначе нельзя прогонять тесты.
- **`aiogram` 3.x** — хендлеры тестируются как обычные корутины.
- **Кризисная проверка детерминированная и до модели** — не зависит от доступности LLM и не поддаётся формулировкам пользователя.
- **`RiskLevel.parse` при неразборчивом значении возвращает `MODERATE`, не `NONE`** — неудачный разбор оценки риска не должен быть неотличим от «риска нет».
- **`Analysis.from_payload` пропускает битые элементы списков, но требует `summary`** — одна испорченная рекомендация не должна обнулять полезный разбор.
- **Кризисный уровень принудительно ставит `needs_professional_help=True`** — независимо от того, что вернула модель.
- **Резервный анализатор не может выдать `CRISIS`** — объявление кризиса остаётся исключительно за детерминированным шлюзом.
- **`analyzer/base.py` и `service.py` сделаны в шаге 3.2, а не 4.1** — короткое замыкание невозможно доказать тестом без протокола анализатора и места, где решается порядок вызовов. Шаг 4.1 сокращён до `fallback.py`.
- **Логика бота отделена от aiogram** (`bot/handlers.py` возвращает список строк, `bot/telegram.py` — единственный адаптер) — иначе ветки ошибок пришлось бы тестировать через объекты фреймворка.
- **Telegram HTML вместо MarkdownV2** — слова пользователя возвращаются в ответе, а `html.escape` — куда меньшая поверхность для ошибок, чем 18 спецсимволов MarkdownV2.
- **`ClaudeAnalyzer` ловит `Exception` широко, но пропускает `CancelledError`** — у всех оставшихся сбоев одна правильная реакция (ответить резервным разбором), а остановка процесса не должна маскироваться под сбой провайдера.
- **В логи пишется только тип исключения и категория сигнала** — ни текст пользователя, ни совпавшая фраза туда не попадают; закреплено тестами.
