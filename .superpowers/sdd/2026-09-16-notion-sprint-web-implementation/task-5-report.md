# Task 5: Web Sprint Lifecycle Report

Implemented owner-only web sprint start and close workflows.

- `POST /projects/{slug}/sprints/{id}/start` commits assigned story points and starts a planning sprint.
- `GET`/`POST /projects/{slug}/sprints/{id}/close` provide an atomic-service-backed close preview and rollover form.
- Forms use CSRF, native dialogs, focus restoration, Escape handling, and submit-button disabling. Close failures re-render without partial mutation.
- Added lifecycle integration coverage and added the two HTML writes to the authorization matrix.

Verification:

- `uv run pytest -v` — 323 passed, 1 deselected
- `uv run ruff check .`
- `uv run ruff format --check .`
- `git diff --check`
- `graphify update .`
