---
name: task-plan
description: Create a numbered task folder under tasks/ with PLAN.md and PROGRESS.md, then execute the plan iteratively, updating PROGRESS.md after every step. Use when the user asks to plan a task, start a new task, make a plan, or execute a plan step by step. Triggers on "make a plan", "план задачи", "новая задача", "execute the plan", "продолжи задачу".
---

# Task planning and iterative execution

Every non-trivial task gets its own folder holding a plan and a live progress log.
The plan is written once and amended deliberately; the progress log is rewritten
after every executed step so that work can be resumed from a cold start.

## 1. Create the task folder

Folder name: `tasks/<DD_MM_YYYY>_<N>/`

- `<DD_MM_YYYY>` — today's date, zero-padded, e.g. `30_08_2026`.
- `<N>` — the increment for that date, starting at `1`.

Pick `N` by listing what already exists for today and taking the highest + 1.
Never reuse or overwrite an existing folder.

```bash
ls tasks/ 2>/dev/null | grep "^30_08_2026_" | sort -t_ -k4 -n | tail -1
```

If `tasks/` does not exist, create it. Two files go in the new folder:
`PLAN.md` and `PROGRESS.md`.

## 2. Write PLAN.md

The plan is the contract. It states what will be built, what is explicitly out of
scope, and the ordered steps. Follow `references/plan-template.md`.

Rules that make a plan usable rather than decorative:

- **Every step names its verification.** A step without a check is not a step,
  it is a wish. Prefer a command whose exit code decides the outcome.
- **Steps are small enough to finish and verify in one go.** If a step needs a
  paragraph to describe, it is two steps.
- **Order by dependency, not by comfort.** Anything the next step imports must
  exist and be tested first.
- **Record what you deliberately are NOT doing** in an "Out of scope" section, so
  a later reader does not mistake omission for oversight.
- **Ask before assuming** when two readings of the request lead to materially
  different plans. Write the resolved answer into the plan.

## 3. Write PROGRESS.md

Created at the same time as the plan, before any code is written. Follow
`references/progress-template.md`. It carries:

- **Status** — one line: which step is in flight, and whether the tree is green.
- **Environment** — versions, interpreter path, how to run the tests. Rebuilding
  this by hand later is the single biggest waste of a resumed session.
- **Executed steps** — append-only, newest last, each with its verification
  result quoted, not paraphrased.
- **Next steps** — the immediate next action, concretely enough to act on.
- **Open questions / blockers** — anything waiting on the user or on an external
  system.
- **Decisions** — choices made mid-flight and the reason, so they are not
  relitigated on resume.

## 4. Execute iteratively

Loop, one step at a time:

1. Read `PROGRESS.md` to find the current step. On a resumed session this is the
   only thing you need to read to know where you are.
2. Implement exactly that step — not the next one, not a nearby cleanup.
3. Run the step's verification command.
4. **Update `PROGRESS.md` before starting the next step.** Quote the real output.
   If the check failed, record the failure and the fix, not just the eventual
   success.
5. Tick the checkbox in `PLAN.md`.

Never batch several steps and update the log once at the end. The value of the
log is that it is correct at every point in between, including after a crash.

### When a step fails

Record the failure in `PROGRESS.md` with the actual error, then fix forward. If
the failure shows the plan itself was wrong, amend `PLAN.md` and say so in the
progress log under Decisions — a silently rewritten plan hides the reason the
work changed shape.

### When the plan turns out to be wrong

Stop, state the problem plainly, and propose the corrected plan. Do not execute
steps you have concluded are harmful just because they are written down.

## 5. Test ordering

When the task involves code, the plan must build tests in this order, and say so:

1. **Unit tests** — pure logic, no I/O, no network, no framework. Fastest and
   most numerous.
2. **Mock tests** — collaborators replaced by fakes. Covers wiring: does the
   handler call the analyzer, does a provider failure degrade correctly.
3. **Integration tests** — real components against real (local) infrastructure:
   a temp database, an in-process bot harness. Slowest and fewest.

A step that adds behaviour adds its unit tests in the same step. Integration
tests come after the units they compose are green.

## Reference files

- `references/plan-template.md` — the PLAN.md skeleton.
- `references/progress-template.md` — the PROGRESS.md skeleton.
