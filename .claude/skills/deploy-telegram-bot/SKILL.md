---
name: deploy-telegram-bot
description: Release a new version of the moodbot Telegram bot — pre-flight checks, local test run against a real bot, and promotion to the long-running instance. Use when asked to launch, test, deploy, release, restart, roll back, or ship a new version of the bot. Triggers on "запустить бота", "выкатить новую версию", "deploy the bot", "restart the bot", "откатить".
---

# Releasing a new version of the bot

Ship order is always the same: **verify locally → run against a test bot →
promote → confirm the promoted instance answers**. Skipping the test bot means
your first real user is the smoke test.

## 0. Two bots, not one

Create a second bot in @BotFather for testing and keep its token in a separate
env file. Debugging a broken release against the bot people actually use is how
a bad afternoon starts.

| | Token in | DB in |
|---|---|---|
| Test | `.env.test` | `moodbot-test.sqlite3` |
| Production | `.env` | `moodbot.sqlite3` |

Both files are gitignored. **Never read a token into the transcript, never paste
one into a command line, never write one into a file the user did not name.**
If a token is missing, tell the user to add it to the env file themselves — do
not ask them to send it.

## 1. Pre-flight

All three must pass before anything is launched. Stop on the first failure.

```bash
.venv/Scripts/python.exe -m pytest -q
```

```bash
.venv/Scripts/python.exe -m pytest --cov=src/moodbot --cov-report=term-missing -q
```

Coverage must not drop below the previous release. If it did, the release adds
untested code — find out what and decide deliberately, do not wave it through.

```bash
.venv/Scripts/python.exe -m moodbot --check
```

`--check` validates configuration and exits without touching the network. It
prints which analyzer is active — confirm it is the one intended for this
release.

## 2. Run against the test bot

```bash
.venv/Scripts/python.exe -m moodbot
```

Long polling; Ctrl+C stops it. Exit codes distinguish the common failures:

| Code | Meaning | Fix |
|------|---------|-----|
| 0 | clean stop (Ctrl+C) | — |
| 2 | configuration error | missing/blank `TELEGRAM_BOT_TOKEN`, bad `MOODBOT_TIMEOUT_SECONDS` |
| 3 | Telegram rejected the token | wrong token in the env file |
| 4 | cannot reach Telegram | network or proxy |

### Manual checklist in the Telegram client

Automated tests cover the logic; this covers the wiring to a real Telegram.
Run every line — the crisis path especially, because it is the one that must
never regress.

- [ ] `/start` — greeting arrives, disclaimer present
- [ ] `/help` — all four commands listed
- [ ] Free text (`"тревожно перед собеседованием, третью ночь не сплю"`) — a structured reply arrives with sections and a disclaimer
- [ ] Second message — the reply reflects the earlier entry
- [ ] `/history` — both entries listed with their dates
- [ ] **Crisis phrase** — the crisis reply arrives with the emergency number, and *no* ordinary "Наблюдения" section
- [ ] A message longer than 4000 characters — a truncation note appears, nothing crashes
- [ ] A non-text message (sticker, photo) — the "I only read text" reply
- [ ] `/delete_me` — confirms, and `/history` afterwards reports nothing stored

If `ANTHROPIC_API_KEY` is set, confirm the reply does **not** carry the
"упрощённый разбор" note — its presence means the model call failed and the
fallback answered.

## 3. Promote

Stop the running production instance, update it, restart it, and confirm it
answers. Never update in place while it is polling — two pollers on one token
fight for updates and both drop messages.

```bash
git pull --ff-only
```

```bash
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Re-run `--check` with the production env before starting. Then start the bot the
way this deployment runs it (see § Running it for real).

**Confirm the promoted instance answers**: send `/start` to the production bot
and see the reply. A deploy that was not verified against the running instance
is a deploy you are guessing about.

## 4. Roll back

```bash
git log --oneline -10
```

```bash
git checkout <previous-tag-or-sha>
```

Then reinstall, `--check`, restart, confirm. The SQLite schema uses versioned
migrations that only add, so rolling the code back does not corrupt an existing
database — but a migration added in the rolled-back version stays applied. If a
release added a migration, say so in the release notes.

## Running it for real

Long polling in a terminal ends when the terminal does. For anything beyond
testing, run it under a supervisor that restarts on failure and on boot.

- **Windows** — Task Scheduler, "At startup", action `\.venv\Scripts\python.exe -m moodbot`, working directory = repo root, "Restart on failure".
- **Linux** — a systemd unit with `Restart=on-failure`, `WorkingDirectory=` the repo, `EnvironmentFile=` the env file, and `User=` a non-root account.

Two operational notes worth writing down once:

- **Exactly one instance per token.** Telegram delivers each update once; a
  second poller silently steals messages. Stop the old one before starting the new.
- **The database is a file.** Back it up before a release that touches
  `storage/`, and remember it holds what users wrote about themselves — it
  deserves the same care as any personal data.

## Reporting the outcome

State plainly which checks ran and what they returned, which checklist items
were exercised by hand, and which were not. If the bot was never started against
a real token — for example because only the user has it — say that rather than
implying the release was verified end to end.
