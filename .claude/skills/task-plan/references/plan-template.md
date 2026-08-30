# PLAN — <task title>

**Created:** <DD.MM.YYYY>
**Folder:** `tasks/<DD_MM_YYYY>_<N>/`
**Progress log:** [PROGRESS.md](PROGRESS.md)

## Goal

One paragraph. What exists at the end that does not exist now, stated so that
someone can tell whether it was achieved.

## Context

What the task depends on: existing code, external services, credentials that must
be present, decisions already taken by the user. Link files as
`[name](../../path/to/file)`.

## Out of scope

Explicit non-goals. Things a reader might reasonably expect to be here and are
deliberately not, with a one-line reason each.

## Constraints and decisions

Resolved ambiguities and the reason for each choice. Anything the user decided
goes here verbatim, so it is not re-litigated later.

## Steps

Each step: one action, one verification. Verification is a command wherever a
command can decide it.

### Stage 1 — <name>

- [ ] **1.1** <action>
  - Verify: `<command>` → <expected outcome>
- [ ] **1.2** <action>
  - Verify: `<command>` → <expected outcome>

### Stage 2 — <name>

- [ ] **2.1** <action>
  - Verify: `<command>` → <expected outcome>

## Test plan

Ordered unit → mock → integration.

| Layer | What it covers | Where |
|-------|----------------|-------|
| Unit | pure logic, no I/O | `tests/unit/` |
| Mock | wiring, degraded paths | `tests/mock/` |
| Integration | real local components | `tests/integration/` |

## Definition of done

A checklist that is checkable, not aspirational. Each line either passes or does
not.

- [ ] <condition>
- [ ] <condition>
