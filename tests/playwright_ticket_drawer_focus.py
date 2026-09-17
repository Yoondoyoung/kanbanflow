"""Run with: /opt/homebrew/opt/python@3.11/bin/python3.11 tests/playwright_ticket_drawer_focus.py"""

import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parents[1]
VENV = ROOT / ".venv" / "bin"


def _step(name: str) -> None:
    print(f"[focus-check] {name}", flush=True)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait(url: str) -> None:
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("server did not start")


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        port = _port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ | {"DATABASE_URL": f"sqlite:///{Path(directory) / 'focus.db'}"}
        subprocess.run(
            [
                str(VENV / "python"),
                "-c",
                (
                    "from app.models import SQLModel; from app.db import get_engine; "
                    "SQLModel.metadata.create_all(get_engine())"
                ),
            ],
            check=True,
            cwd=ROOT,
            env=env,
        )
        server = subprocess.Popen(
            [str(VENV / "uvicorn"), "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _step("waiting for disposable app")
            _wait(base_url)
            with sync_playwright() as playwright:
                _step("launching Chromium")
                browser = playwright.chromium.launch()
                page = browser.new_page()
                page.set_default_timeout(5_000)
                page.set_default_navigation_timeout(5_000)
                _step("registering account")
                page.goto(f"{base_url}/register")
                page.locator("#register-name").fill("Ada")
                page.locator("#register-email").fill("ada@example.com")
                page.locator("#register-password").fill("secure-password")
                page.get_by_role("button", name="Create account").click(no_wait_after=True)
                page.wait_for_url("**/dashboard")
                _step("creating project")
                page.get_by_role("button", name="New project").click()
                page.locator("#project-name").fill("Focus project")
                page.locator("#project-dialog .app-primary-button").click(no_wait_after=True)
                page.wait_for_url("**/projects/focus-project/backlog")
                _step("creating sprint")
                csrf_token = page.locator("input[name=_csrf]").first.input_value()
                page.evaluate(
                    """async csrfToken => {
                        const response = await fetch('/projects/focus-project/sprints', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                            body: new URLSearchParams({
                                _csrf: csrfToken, name: 'Focus sprint', goal: 'Focus test',
                                start_date: '2026-09-21', end_date: '2026-09-28'
                            })
                        });
                        if (!response.ok) {
                            throw new Error(`sprint setup failed: ${response.status}`);
                        }
                    }""",
                    csrf_token,
                )
                page.goto(f"{base_url}/projects/focus-project/backlog")
                board_url = page.locator("#sprint-selector option").first.get_attribute("value")
                page.goto(f"{base_url}{board_url}")
                _step("creating ticket")
                page.get_by_role("button", name="New ticket").click()
                page.locator("#ticket-title").fill("Keep focus")
                page.locator("#ticket-modal .app-primary-button").click()
                card = page.locator(".ticket-card-open").first
                card.wait_for()
                old_card = page.locator(".ticket-card").first.element_handle()
                assert old_card is not None
                _step("opening centered modal")
                card.click()
                panel = page.locator("#ticket-detail-panel")
                panel.wait_for()
                box = panel.bounding_box()
                viewport = page.viewport_size
                assert box is not None and viewport is not None
                assert abs(box["x"] + box["width"] / 2 - viewport["width"] / 2) < 2
                assert abs(box["y"] + box["height"] / 2 - viewport["height"] / 2) < 2
                form_box = page.locator(".ticket-detail-form").bounding_box()
                comments_box = page.locator("#ticket-comments").bounding_box()
                assert form_box is not None and comments_box is not None
                assert comments_box["x"] > form_box["x"] + form_box["width"]
                _step("saving modal")
                page.locator("#ticket-detail-panel button", has_text="Save changes").click()
                page.locator("#ticket-detail-panel [role=status]").wait_for()
                page.wait_for_function("card => !card.isConnected", arg=old_card)
                _step("adding a comment")
                comment_input = page.locator("#new-comment-body")
                comment_input.fill("@Ad")
                mention_menu = page.locator("#new-comment-mentions")
                mention_menu.wait_for(state="visible")
                comment_input.press("Enter")
                assert comment_input.input_value() == "@Ada "
                assert page.locator(
                    '.ticket-comment-form input[name="mention_ids"]'
                ).count() == 1
                comment_input.fill("Ready for review")
                assert page.locator(
                    '.ticket-comment-form input[name="mention_ids"]'
                ).count() == 0
                comment_input.fill("@Ad")
                mention_menu.wait_for(state="visible")
                comment_input.press("Enter")
                comment_input.type("Ready for review")
                page.get_by_role("button", name="Comment", exact=True).click()
                page.locator(".ticket-comment", has_text="Ready for review").wait_for()
                comment = page.locator(".ticket-comment", has_text="Ready for review")
                actions_box = comment.locator(".ticket-comment-actions").bounding_box()
                comment_box = comment.bounding_box()
                body_box = comment.locator(".ticket-comment-body").bounding_box()
                assert actions_box is not None and comment_box is not None and body_box is not None
                assert actions_box["x"] > comment_box["x"] + comment_box["width"] / 2
                assert actions_box["y"] < body_box["y"]
                assert comment.locator(".ticket-comment-mentions").count() == 0
                comment_time = comment.locator("time")
                raw_time = comment_time.get_attribute("datetime")
                expected_time = page.evaluate(
                    "value => new Intl.DateTimeFormat([], "
                    "{dateStyle: 'medium', timeStyle: 'short'}).format(new Date(value))",
                    raw_time,
                )
                assert comment_time.inner_text() == expected_time
                _step("closing modal and checking focus")
                page.get_by_role("button", name="Close").click()
                page.locator("#ticket-detail-panel").wait_for(state="detached")
                assert card.evaluate("element => element === document.activeElement")
                _step("checking full-screen mobile modal")
                page.set_viewport_size({"width": 390, "height": 844})
                card.click()
                panel.wait_for()
                mobile_box = panel.bounding_box()
                assert mobile_box is not None
                assert mobile_box["x"] == 0 and mobile_box["y"] == 0
                assert mobile_box["width"] == 390 and mobile_box["height"] == 844
                mobile_form_box = page.locator(".ticket-detail-form").bounding_box()
                mobile_comments_box = page.locator("#ticket-comments").bounding_box()
                assert mobile_form_box is not None and mobile_comments_box is not None
                assert mobile_comments_box["y"] > mobile_form_box["y"] + mobile_form_box["height"]
                page.get_by_role("button", name="Close").click()
                browser.close()
                _step("passed")
        except Exception as error:
            print(f"[focus-check] failed: {error!r}", flush=True)
            print(f"[focus-check] current URL: {page.url}", flush=True)
            raise
        finally:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
