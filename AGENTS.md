# Smart Shop Development Protocol

## Purpose
This file defines how coding agents must work in the Smart Shop repository.

## Product AI Scope
The Smart Shop product AI agent is **FUTURE / OUT OF CURRENT SCOPE**. Do not implement or design LangChain, LangGraph, OpenAI agent functionality, Tavily, agent memory, AI endpoints, or AI workflows until the main Smart Shop business application is complete, tested, secured, and production-ready.

## Context Loading — Usage Efficient
Reading files consumes model/agent context and usage. Do not perform a full repository read for ordinary tasks.

Before coding:
1. Read `project/STATUS.md`.
2. Read `project/DECISIONS.md` when business/architecture constraints matter.
3. Read only the relevant module/architecture documents.
4. Inspect only the source files and tests directly relevant to the task.
5. Expand context only when required by dependencies or tests.

Do not repeatedly reread unchanged files already understood in the current task.

## Source-of-Truth Order
When sources disagree, use:
1. actual source code
2. tests
3. models/migrations
4. current working-tree state
5. `project/STATUS.md`
6. `project/ROADMAP.md`
7. `project/PROJECT.md`
8. architecture/module documentation
9. older Git history

Report meaningful conflicts instead of silently implementing stale documentation.

## Safety Rules
- Preserve existing working-tree changes.
- Never reset, revert, checkout, clean, stash, or discard user changes without permission.
- Do not overwrite unrelated files.
- Work on one logical task at a time.
- Do not rebuild functionality that already exists.
- Do not silently change business rules.
- Preserve authentication, authorization, customer isolation, database relationships, and historical records.
- Prefer the smallest safe change.
- Do not commit unless explicitly instructed.

## High-Risk Areas
Treat these as high-risk and require deliberate reasoning/tests:
- payments
- credit
- inventory
- financial reports
- authorization/customer isolation
- concurrency
- transaction boundaries
- historical financial data

## Implementation
Before changing code, identify:
- current implementation
- dependencies
- affected files
- relevant tests
- transaction/data-integrity implications
- likely side effects

Do not combine unrelated features in one task.

## Validation
For backend changes, run appropriate focused Django tests plus, when available:
- `python manage.py check`
- `python manage.py makemigrations --check`
- `git diff --check`

For JavaScript changes:
- `node --check <changed-file>`

Review:
- `git diff`
- `git status --short`

Do not install dependencies merely to broaden a recovery/read task unless explicitly instructed.

## Documentation Is Part Of The Task
A task is NOT complete until `project/STATUS.md` is updated with:
- task completed
- files changed
- tests/checks performed
- results
- known issues
- next task
- minimum context required for the next task

Update `project/DECISIONS.md` when a durable architectural/business decision is established.
Update `project/PROJECT.md` only for stable product/architecture information.
Update `project/ROADMAP.md` when the development plan changes.

Do not create duplicate trackers such as `TASKS.md`, `PROGRESS.md`, `CURRENT_TASK.md`, `NEXT_TASK.md`, or `AGENT_MEMORY.md`.

## Handoff
Before stopping, report:
- Current phase
- Completed
- Files changed
- Tests/checks
- Known issues
- Next recommended task
- Minimum files/context needed for that task

Then stop.
