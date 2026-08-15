

Pasted markdown(1).md
File


Pasted markdown(2).md
File

Pasted markdown (2).md
File
is not time to update agent.md
## Backend Documentation Result

The official backend architecture document has been created/updated in MADAM_HY_BACKEND.md based strictly on the repository state and the required backend boundaries.

## File

- MADAM_HY_BACKEND.md

## Sections Included

- Project Overview
- Architecture Principles
- Business Rules
- Roles and Access
- Backend Modules
- Current Implementation Status
- Database Design Principles
- Product Boundary
- Inventory Boundary
- Sales / POS Boundary
- Orders Boundary
- Payments Boundary
- Credits Boundary
- Expenses Boundary
- Requests Boundary
- Reports Boundary
- Activity Logs
- Notifications
- Migration Safety
- Testing Requirements
- Backend Development Roadmap
- Phase Rules
- Current Repository State
- Summary

## Current Backend Status

- Accounts: COMPLETE
- Products: COMPLETE
- Inventory: NEXT
- Sales/POS: PLANNED
- Orders: PLANNED
- Payments: PLANNED
- Credits: PLANNED
- Expenses: PLANNED
- Requests: PLANNED
- Reports: PLANNED
- Notifications: PLANNED
- Activity Logs: PLANNED
- Customer backend integration: PLANNED

## Next Backend Phase

- Inventory Foundation — NEXT

## Verification

Verified by:
- reading the repository’s current Accounts and Products implementations
- reviewing AGENTS.md and MADAM_HY_FRONTEND.md
- checking the current working tree with git status --short

Evidence from the repo check showed the existing mixed/uncommitted state and confirmed the doc was the only file changed in this documentation task.

Yes. That's actually better. You can copy and paste one prompt into Copilot, let it update only AGENTS.md, then bring me the result. I won't make you spend extra turns on unnecessary checks.

Use this exact prompt:

Update ONLY AGENTS.md.

Do not modify any other file.
Do not create any new file.
Do not commit.
Do not push.

First read:
- AGENTS.md
- docs/MADAM_HY_FRONTEND.md
- docs/MADAM_HY_BACKEND.md

The actual repository is the source of truth.

The project has now moved from the FRONTEND DEVELOPMENT phase to the BACKEND DEVELOPMENT phase.

Update AGENTS.md so it accurately reflects this transition.

IMPORTANT:
Do not copy the entire contents of MADAM_HY_FRONTEND.md or MADAM_HY_BACKEND.md into AGENTS.md.

AGENTS.md should remain the high-level instruction file for the entire project.

It should reference the detailed documentation files instead.

The documentation hierarchy should be:

AGENTS.md
→ project-wide rules and instructions

docs/MADAM_HY_FRONTEND.md
→ frontend-specific rules

docs/MADAM_HY_BACKEND.md
→ backend-specific rules and roadmap


AGENTS.md must reflect these current facts:

PROJECT:
That's enough for this step. Don't ask Copilot to do anything else yet.

Once it finishes, paste its response here. I'll tell you if anything important is missing before we start Inventory.


waht i mean is you crating it so i can copy and paste it just tell me where to past it

Ah, yes — I understand now. You want me to prepare the prompt, and you only want me to tell you where to paste it in Copilot, without having to figure out the placement yourself.

For the prompt I gave you:

Where to paste it
Since you're using GitHub Copilot in VS Code:

Open your smart_shop project in VS Code.

Open Copilot Chat.

Select Agent mode (not Ask/Edit mode).

Paste the entire prompt into the Copilot Chat box.

Send it.

The prompt will tell Copilot to update only AGENTS.md.

Important
Because your repository has now moved into the backend phase, don't let Copilot start Inventory yet.

First let it update AGENTS.md.

Then send me Copilot's response here. I'll review it and, if anything is missing, I'll give you the next copy-and-paste prompt.

We'll work like this from now on:

Me → prepare exact prompt → You paste into Copilot Agent → Copilot works → You paste result here → I review → next prompt.

That will save your Copilot usage and prevent unnecessary tasks.


not the prompt the file it selfe

Yes — this is the file itself.

Where to put it
Download the prepared file:


Then in your project:

smart_shop/
├── AGENTS.md          ← replace/update this one
├── docs/
│   ├── MADAM_HY_FRONTEND.md
│   └── MADAM_HY_BACKEND.md
├── apps/
├── config/
├── templates/
└── static/
So put AGENTS.md in the root of your smart_shop project, at the same level as manage.py.

Important
Do not put it inside:

apps/
docs/
config/
templates/
static/
It should be:

C:\Users\ADMIN\OneDrive\Desktop\smart_shop\AGENTS.md
You can replace your current AGENTS.md with the file I prepared.

After that, don't ask Copilot to do anything yet. Show me the current git status and we'll make sure the documentation change itself is safe before moving to the Inventory backend.


Library
/
AGENTS.md


MADAM HY — Project Instructions
1. Project Overview
MADAM HY is a Django-based retail/shop management and customer commerce system.

Technology:

Python

Django

MySQL

Django ORM

Django Templates

HTML

CSS

JavaScript

AJAX

The repository is developed in clearly separated frontend and backend phases.

2. Source of Truth
The actual repository is the source of truth.

Before making changes:

Inspect the existing repository.

Read the relevant documentation.

Inspect the current implementation.

Check git status.

Do not recreate existing architecture.

If documentation conflicts with the repository:

Inspect the code first.

Identify the discrepancy.

Preserve working architecture.

Report the discrepancy.

Do not blindly overwrite existing work.

Do not create duplicate files or folders.

Do not rename or move existing files unless explicitly instructed.

3. Documentation
Frontend
Detailed frontend rules and architecture:

docs/MADAM_HY_FRONTEND.md

Backend
Detailed backend architecture, business rules, module boundaries, database principles, testing requirements, and roadmap:

docs/MADAM_HY_BACKEND.md

AGENTS.md is the high-level project instruction file and should not unnecessarily duplicate those documents.

4. Current Development Phase
FRONTEND
COMPLETE

The completed frontend modules include:

Accounts

Dashboard

Products

Inventory

Sales/POS

Orders

Payments

Credits

Expenses

Reports

Requests

Customer

Do not redesign completed frontend modules unless explicitly instructed.

BACKEND
ACTIVE

Current backend phase:

Inventory Foundation — NEXT

Backend development must proceed one phase at a time.

Do not implement future backend modules early.

5. Backend Roadmap
Accounts Foundation — COMPLETE

Products Foundation — COMPLETE

Inventory Foundation — NEXT

Sales/POS — PLANNED

Orders — PLANNED

Payments — PLANNED

Credits — PLANNED

Expenses — PLANNED

Requests — PLANNED

Activity Logs / Notifications — PLANNED

Reports — PLANNED

Customer Backend Integration — PLANNED

A module must not be marked COMPLETE until it has actually been implemented and verified in the repository.

For detailed backend rules, follow:

docs/MADAM_HY_BACKEND.md

6. Backend Module Boundaries
Keep responsibilities separated between:

Accounts

Products

Inventory

Sales/POS

Orders

Payments

Credits

Expenses

Requests

Reports

Notifications

Activity Logs

Customer backend

Important boundaries:

Do not put inventory stock logic inside Products.

Do not duplicate transactional data unnecessarily for Reports.

Do not move responsibilities between modules without reviewing docs/MADAM_HY_BACKEND.md.

Do not implement a future module merely because another module depends on it conceptually.

7. Confirmed Business Rules
Preserve these confirmed rules:

OWNER has full system access.

MANAGER, CASHIER, STAFF, and CUSTOMER have restricted access.

Customers may use credit only when they have an approved credit allowance.

Staff are not assigned to orders.

The business currently operates one shop/location.

Products support multiple images.

Product price changes must preserve historical pricing.

Supported payment methods are:

CASH

BANK_TRANSFER

CARD

CREDIT

Do not invent additional business rules without explicit instruction.

For detailed rules, consult:

docs/MADAM_HY_BACKEND.md

8. Frontend Rules
Frontend development is complete.

For frontend-specific work, follow:

docs/MADAM_HY_FRONTEND.md

The frontend uses an established shared design system.

Reuse:

core CSS

existing components

existing layout patterns

existing responsive patterns

existing JavaScript conventions

Do not duplicate generic core CSS styles unnecessarily.

Do not recreate existing templates, components, folders, or assets.

Any future frontend changes must remain narrowly scoped.

9. Backend Development Rules
Backend work must:

Follow the existing Django architecture.

Reuse existing models and relationships where appropriate.

Avoid unnecessary abstractions.

Avoid unnecessary dependencies.

Preserve existing data.

Keep module boundaries clear.

Implement only the current phase.

Avoid modifying completed modules unless required by the current phase.

Before changing backend code, inspect:

existing models

migrations

admin configuration

views

URLs

settings

tests

related module boundaries

Do not assume that a missing feature means a new model or app is required.

10. Database and Migration Safety
Never:

Drop the database to solve migration problems.

Delete migrations casually.

Fake migrations without understanding the migration state.

Reset working migrations destructively.

Remove existing data to make a migration easier.

Always:

Inspect existing migrations.

Run python manage.py makemigrations when model changes are made.

Review generated migrations.

Run python manage.py migrate.

Run python manage.py check.

Run relevant tests.

Resolve migration conflicts explicitly.

Database changes must preserve existing data and existing working functionality.

11. Testing Requirements
After backend changes, run the relevant checks.

At minimum where applicable:

python manage.py check
python manage.py test <relevant_app>
git diff --check
For JavaScript changes:

node --check <relevant-file>
Do not claim a phase is complete unless the relevant verification has actually been performed.

If a check cannot run because of the local environment:

Report the exact error.

Do not modify the environment unless explicitly instructed.

12. Git Rules
Before committing:

git status
git diff --name-only
git diff --check
Verify that only files belonging to the current phase are included.

Do not commit unrelated work.

Do not use destructive Git commands to remove work that may belong to another phase.

Do not push to GitHub unless explicitly instructed.

When a phase is complete:

Report the commit hash.

Report the commit message.

Report the files included.

Report the final git status.

13. Scope Discipline
Every task must remain strictly scoped.

If asked to work on Inventory:

Work only on Inventory and the minimum required integration.

Do not start Sales/POS.

Do not start Orders.

Do not start Payments.

Do not start Credits.

Do not start Expenses.

Do not start Requests.

Do not start Reports.

Do not start Customer backend integration.

If a required dependency belongs to a future phase, stop and report it rather than silently implementing the future phase.

14. Change Management
Before editing:

Inspect.

Plan.

Identify the exact files that need changes.

During editing:

Modify only necessary files.

Preserve established architecture.

Avoid unrelated cleanup.

Avoid redesigning completed work.

After editing:

Run relevant verification.

Inspect the final diff.

Confirm scope.

Report any remaining issues.

15. Current Repository State
The frontend has been completed across the established modules.

Backend foundations currently completed:

Accounts Foundation

Products Foundation

Backend work now proceeds with:

Inventory Foundation

The repository may contain earlier or mixed working-tree changes. Do not assume every uncommitted file belongs to the current phase.

Always inspect git status and git diff before committing.

16. Phase Completion Standard
A backend phase is COMPLETE only when:

Required models and backend logic are implemented.

Required migrations are created and applied safely.

Admin configuration is complete where appropriate.

Relevant tests pass.

python manage.py check passes.

git diff --check passes.

The final diff is scoped correctly.

No unrelated work is committed.

Remaining limitations are documented.

17. Priority Rule
When instructions conflict, use this priority:

Explicit current user instruction

Existing repository architecture

AGENTS.md

docs/MADAM_HY_BACKEND.md

docs/MADAM_HY_FRONTEND.md

General implementation preferences

Never silently make architectural decisions that contradict the current repository.

18. Immediate Next Task
The next backend task is:

Inventory Foundation

Before implementing it:

Read AGENTS.md.

Read docs/MADAM_HY_BACKEND.md.

Inspect the existing Inventory app.

Inspect Products because Inventory depends on Product records.

Inspect existing migrations.

Check git status.

Confirm the exact Inventory scope.

Then implement only the Inventory Foundation.
