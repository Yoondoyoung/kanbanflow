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
                "from app.models import SQLModel; from app.db import get_engine; SQLModel.metadata.create_all(get_engine())",
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
                        if (!response.ok) throw new Error(`sprint setup failed: ${response.status}`);
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
                _step("opening drawer")
                card.click()
                page.locator("#ticket-detail-panel").wait_for()
                _step("saving drawer")
                page.locator("#ticket-detail-panel button", has_text="Save changes").click()
                page.locator("#ticket-detail-panel [role=status]").wait_for()
                _step("closing drawer and checking focus")
                page.get_by_role("button", name="Close").click()
                page.locator("#ticket-detail-panel").wait_for(state="detached")
                assert card.evaluate("element => element === document.activeElement")
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
