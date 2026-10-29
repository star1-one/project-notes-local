# Repository guidance

## Start here

Read `README.md` and `HANDOFF.md` before changing the application. This repository is a macOS local project assistant built with Python 3.10+, SQLite, and static HTML/CSS/JavaScript. Continue the existing implementation rather than replacing it with a new app.

## Data and publication boundaries

- Keep this repository source-only. Do not commit `data/`, database files and sidecars, imported documents, mail/chat contents, exports, backups, credentials, cookies, or local environment files.
- Use temporary directories and synthetic fixtures for tests. Do not inspect real work materials or authentication files to debug tests.
- Preserve the user's stored data. Do not reset, replace, migrate, or delete a data directory as a routine setup step.
- Keep account-specific settings and local machine details out of public documentation, logs, screenshots, and issues.
- Add only explicit intended files when committing; review the staged diff and file list before publishing.

## Behavior to preserve

- Enforce project scope in all source, conversation, search, and generation paths. A project must not retrieve or display another project's content.
- Preserve source dates, references, and retrieval coverage. Distinguish facts from suggestions; an assistant draft is not evidence of real sending or approval.
- Mail/chat ingestion stays manual and generated replies are drafts. There is no automatic sending.
- Reuse the official Codex CLI's ChatGPT login. Keep the API-key refusal and do not silently switch billing methods, model providers, or remote services.
- Current AI generation sends selected context to OpenAI. Do not describe it as fully offline or claim training exclusion from local CLI flags. Training and retention settings belong to the active account and service.
- Do not silently enable local-model mode, add model downloads, or add email/chat integrations while doing ordinary maintenance.
- Keep loopback-only serving, Host/Origin/CSRF checks, safe text rendering, bounded document extraction, single-instance data locking, and completed-response-only persistence.

## Validation

Create/use `.venv` and run:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Use the checks relevant to the change. For UI changes, verify the affected browser flow and project switching with synthetic content. `tests/live_smoke.py` makes a real subscription request and is an explicit optional check, not part of normal unit tests. Do not repeat real requests once their relevant concern is resolved.

Update `HANDOFF.md` when setup, behavior, limitations, or verified state changes. Report what was tested on the current machine separately from historical validation.
