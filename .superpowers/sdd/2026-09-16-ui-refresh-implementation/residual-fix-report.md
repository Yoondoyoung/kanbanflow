# Residual UI verification remediation

## Root cause

- Native ticket saves redirected to the normal detail URL, which rendered with `saved=False` and therefore had no textual confirmation.
- The settings link received `is-active` and `aria-current="page"`, but no active CSS treatment.
- The focus check kept a Playwright `Locator`; after HTMX replaced the card, that locator silently resolved to the replacement.

## RED

Command:

```sh
uv run pytest tests/test_web_final_fixes.py::test_non_htmx_detail_post_redirects_to_a_saved_full_page tests/test_web_ui_refresh.py::test_settings_link_has_current_location_state -q
```

Result: 2 failures. The redirect location lacked `?saved=true`; the active settings selector was absent.

## GREEN

Native saves now redirect to the detail URL with `?saved=true`; the GET passes that flag to the existing ticket-detail renderer, which emits the existing `role="status"` message. HTMX save and validation/error paths remain unchanged. The active settings link uses the existing text semantic token for its color and underline.

The focused RED/GREEN command passed after the change: `2 passed`.

Scoped pytest verification:

```sh
uv run pytest tests/test_web_final_fixes.py tests/test_web_ui_refresh.py tests/test_web_ticket_detail.py -q
```

Result: `37 passed`.

## Browser

```sh
/opt/homebrew/opt/python@3.11/bin/python3.11 tests/playwright_ticket_drawer_focus.py
```

Result: passed. The script retains the pre-save `.ticket-card` element handle and waits until `!card.isConnected` before closing the drawer and asserting focus via the current card locator.

## Lint and diff

```sh
uv run ruff check app/routers/web.py tests/test_web_final_fixes.py tests/test_web_ui_refresh.py tests/playwright_ticket_drawer_focus.py
git diff --check
```

Result: Ruff reported `All checks passed!`; `git diff --check` exited successfully with no output.

## Scope

No graphify or full-suite run was performed, per the brief.
