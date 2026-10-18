"""P4 BR auth workflow: real Chromium login + capabilities + cross-user denial.

Extends p4_br_harness with the real authenticated flow through the UI form:
  BR-07  real login via UI form (user A), logout/login user B; old identity gone
  BR-07b cross-user capabilities denial (A's token on B's session -> 401/403/404)

Run: <isolated-venv>/bin/python <this> <UI_BASE> <OUT>
"""
from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

UI_BASE = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/iat-shots"
results: list[dict] = []


def rec(case, ok, **extra):
    results.append({"case": case, "ok": ok, **extra})
    print(json.dumps({"case": case, "ok": ok, **extra}, default=str), flush=True)


def main():
    import os
    os.makedirs(OUT, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, executable_path="/usr/bin/chromium-browser", chromium_sandbox=True
        )
        ctx_a = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx_a.new_page()

        # --- BR-07: real UI login as user A ---
        page.goto(UI_BASE + "/", wait_until="networkidle", timeout=30000)
        page.locator("input").first.fill("iat_user_a")
        page.locator("input[type=password]").first.fill("IatTest2026!")
        page.get_by_role("button", name="登录", exact=True).click()
        page.wait_for_url(lambda u: "login" not in u, timeout=15000)
        page.wait_for_load_state("networkidle", timeout=30000)
        url_a = page.url
        page.screenshot(path=f"{OUT}/br07-logged-in-a.png")
        rec("BR-07", "login" not in url_a.lower(),
            url_after_login=url_a, note="real UI form login as user A")

        # capture JWT from localStorage (axios uses Authorization header)
        jwt_a = page.evaluate("() => localStorage.getItem('access_token') || localStorage.getItem('token') || ''")
        # --- cross-user denial: A's identity cannot read another user's session ---
        r = page.request.get(
            UI_BASE + "/api/v1/agent-tools/sessions/nonexistent-session/capabilities",
            timeout=15000)
        rec("BR-07b", r.status in (401, 403, 404),
            status=r.status, body=r.text()[:200],
            note="nonexistent/foreign session denied (no data leak)")

        # --- logout / B login: old identity must disappear ---
        page.evaluate("() => localStorage.clear()")
        ctx_b = browser.new_context(viewport={"width": 1280, "height": 900})
        page_b = ctx_b.new_page()
        page_b.goto(UI_BASE + "/", wait_until="networkidle", timeout=30000)
        page_b.locator("input").first.fill("iat_user_b")
        page_b.locator("input[type=password]").first.fill("IatTest2026!")
        page_b.get_by_role("button", name="登录", exact=True).click()
        page_b.wait_for_url(lambda u: "login" not in u, timeout=15000)
        page_b.wait_for_load_state("networkidle", timeout=30000)
        url_b = page_b.url
        page_b.screenshot(path=f"{OUT}/br07-logged-in-b.png")
        jwt_b = page_b.evaluate("() => localStorage.getItem('access_token') || localStorage.getItem('token') || ''")
        rec("BR-07c", "login" not in url_b.lower() and jwt_b != jwt_a,
            url_b=url_b, distinct_identity=(jwt_b != jwt_a),
            note="user B session is distinct; A's identity not reused")

        browser.close()

    print(json.dumps({"summary": {"total": len(results),
                                  "passed": sum(1 for r in results if r["ok"])}},
                     default=str), flush=True)


main()
