---
name: python-tdd
description: Conventions for Python code and the unit → mock → integration test layering used in this repo, plus how to run the suite on Windows. Use when writing, changing, or testing Python in this project, or when deciding which test layer something belongs in.
---

# Python and testing conventions

## Layout

```
src/moodbot/          importable package — no side effects at import time
tests/unit/           pure logic
tests/mock/           one real component, faked collaborators
tests/integration/    real components, local infrastructure only
```

`pyproject.toml` holds dependencies and pytest configuration. The package is
installed editable (`pip install -e ".[dev]"`) so tests import it by name rather
than by path manipulation.

## Code

- **Type-annotate public functions.** Annotations are the cheapest documentation
  that stays true.
- **No I/O at import time.** No database connections, no network, no reading env
  vars into module-level constants. Configuration is loaded by an explicit call,
  which is what makes the code testable without monkeypatching the world.
- **Dependencies are passed in, not reached for.** A handler receives its
  analyzer and its repository; it does not construct them. This is what lets the
  mock layer exist at all.
- **Secrets come from the environment.** Never a literal in source, never a
  default value in code, never written to a log or an error message. `.env` is
  gitignored and is for local development only.
- **Fail loudly on programmer error, degrade gracefully on external failure.** A
  missing required config is a startup crash. A provider timeout is a caught
  exception and a fallback response.

## Which layer does a test belong in?

Ask what the test would catch if it broke.

| The test exercises | Layer | Rule of thumb |
|---|---|---|
| A pure function's return value | `unit` | No fixtures heavier than a dataclass |
| Branching, parsing, validation, scoring | `unit` | Should run in microseconds |
| "Does A call B correctly" | `mock` | B is a fake with recorded calls |
| Degraded paths: timeout, refusal, malformed response, DB locked | `mock` | This is the layer that earns its keep |
| Schema, migrations, real SQL | `integration` | Temp file DB, torn down after |
| Handler → analyzer → storage end to end | `integration` | In-process, no live network |

Two failure modes to avoid:

- A "unit test" that needs six mocks. That is a design smell in the code under
  test, not a testing problem — the function is doing too much.
- An integration test standing in for missing unit tests. When it fails you learn
  that something is broken, not what.

## Hard rules for tests

- **No network. Ever.** Not in any layer. If a test would call the Anthropic API
  or Telegram, it needs a fake. A test suite that needs an API key is a test
  suite that does not run in CI.
- **No real credentials**, including in fixtures. Use obvious placeholders that
  cannot be mistaken for real ones.
- **Deterministic.** No `datetime.now()` in assertions, no random without a seed,
  no dependence on dict ordering across runs. Inject a clock.
- **Each test names the behaviour, not the function.** `test_crisis_phrase_short_circuits_llm`
  beats `test_analyze_2`.
- **Assert on behaviour, not on call counts**, unless the call count *is* the
  behaviour (e.g. "the LLM is not called when a crisis phrase matched").

## Running the suite (Windows)

The interpreter is a real CPython install, not the Microsoft Store stub. Use the
venv's executable directly rather than relying on `activate`:

```bash
.venv/Scripts/python.exe -m pytest -q
```

Per layer:

```bash
.venv/Scripts/python.exe -m pytest tests/unit -q
```

With coverage:

```bash
.venv/Scripts/python.exe -m pytest --cov=src/moodbot --cov-report=term-missing -q
```

If `python` on PATH prints "Python was not found", it is the Store alias
shadowing the real install — call the venv executable by path.

## Definition of a finished change

- The new behaviour has a unit test that fails without the change.
- Degraded paths for anything crossing a process boundary have a mock test.
- The full suite is green, not just the tests you were looking at.
- No secret, token, or personal message content is written to a log.
