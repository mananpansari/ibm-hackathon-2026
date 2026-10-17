"""Drive the app on the VM (through an SSH tunnel to localhost:8001) with Playwright:
customer question flow (UI v2: Q1 -> Q2 -> Q3), the full demo replay (timed), the officer case view
and outcome form, the live box, screenshots and a video.

    python record_demo.py <out_dir>
"""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://localhost:8001")  # BASE=http://127.0.0.1:8010 for a local run
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
STEP_S = float(os.environ.get("STEP_S", 5.0))  # pause per demo payment, so 13 payments plus intro fit about 90 s of narration
LIVE = {  # a wallet Tether froze before 2024 (not in our histories) and a busy exchange hot wallet
    "not_in_snapshot": "0xac97e9d9f9111613df8cabbf6435f70139528882",
    "exchange": "0x28c6c06298d514db089934071355e5743bf21d60",
}
report = {}

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 860}, record_video_dir=str(OUT / "video"),
                              record_video_size={"width": 1280, "height": 860})
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    # 1. Customer question flow (the default customer, mrs-tan, is the video's Tan Siew Lian)
    def answer(qid, *ids, text=None):
        page.wait_for_selector(f"#result.question input[name={qid}]")
        for i in ids:
            page.check(f"#result input[name={qid}][value={i}]")
        if text:
            page.fill("#answer", text)

    page.goto(BASE + "/")
    page.fill("#wallet", "0x" + "ab" * 20)
    page.fill("#amount", "20000")
    page.click("button[type=submit]")
    answer("why", "officer", text="The police officer said my account is linked to a crime and I must move my savings to this safe wallet. He said not to tell the bank.")
    page.screenshot(path=str(OUT / "1-customer-question.png"), full_page=True)
    report["question"] = page.inner_text("#result")
    page.click("#result button:has-text('Continue')")
    answer("how", "phone")
    page.click("#result button:has-text('Continue')")
    answer("asked", "secret", "act_fast")
    page.screenshot(path=str(OUT / "1c-customer-q3.png"), full_page=True)
    t0 = time.monotonic()
    page.click("#result button:has-text('Continue')")
    page.wait_for_selector("#result.hold", timeout=15000)
    report["answer_to_hold_s"] = round(time.monotonic() - t0, 2)
    page.screenshot(path=str(OUT / "2-customer-hold.png"), full_page=True)
    report["hold"] = page.inner_text("#result")
    report["demo_strip"] = page.inner_text("#demo-line")

    # 2. Demo spine on the officer page, timed
    page.goto(BASE + "/officer")
    page.click("#reset")
    page.wait_for_function("document.getElementById('demo-status').textContent.includes('reset')")
    start, steps = time.monotonic(), []
    for i in range(1, 30):
        page.click("#next")
        page.wait_for_function(f"document.getElementById('demo-status').textContent.startsWith('Payment {i}:') || "
                               "document.getElementById('demo-status').textContent.startsWith('Replay finished')")
        status = page.inner_text("#demo-status")
        steps.append(status)
        if status.startswith("Replay finished"):
            break
        page.wait_for_timeout(int(STEP_S * 1000))
        if "confirms the scam" in status:
            page.screenshot(path=str(OUT / "3-officer-confirm.png"), full_page=True)
    report["demo_seconds"] = round(time.monotonic() - start, 1)
    report["demo_steps"] = steps
    page.screenshot(path=str(OUT / "4-officer-final.png"), full_page=True)
    report["queue_rows"] = page.locator("#queue tr").count()
    report["queue_summary"] = page.inner_text("#summary")
    # claim the top case: the case view and the outcome form are submission screenshots
    page.click("#queue tr button:has-text('Claim')")
    page.wait_for_selector("#v-case:not([hidden]) h3")
    page.wait_for_timeout(800)  # let the money-flow graph lay out
    page.screenshot(path=str(OUT / "6-officer-case.png"), full_page=True)
    report["why_card"] = page.inner_text("#v-case")[:1500]
    page.click("#v-case button:has-text('Record outcome')")
    page.wait_for_selector("#v-outcome:not([hidden]) form")
    page.check("input[name=call][value=confirmed_identity]")
    page.check("input[name=decision][value=cancel]")
    page.select_option("select[name=reason]", "confirmed_impersonation")
    page.screenshot(path=str(OUT / "7-officer-outcome.png"), full_page=True)
    page.click("#v-outcome button:has-text('Submit decision')")
    page.wait_for_selector("#v-queue:not([hidden])")
    report["queue_rows_after_outcome"] = page.locator("#queue tr").count()

    # 3. Live box
    for name, addr in LIVE.items():
        if not addr:
            continue
        page.fill("#live-wallet", addr)
        t0 = time.monotonic()
        page.click("#live button")
        page.wait_for_function("!document.getElementById('live-out').textContent.startsWith('checking')", timeout=20000)
        report[f"live_{name}"] = {"seconds": round(time.monotonic() - t0, 2), "shown": page.inner_text("#live-out")}
        page.screenshot(path=str(OUT / f"5-live-{name}.png"), full_page=True)

    report["console_errors"] = errors
    ctx.close()
    browser.close()

(OUT / "report.json").write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1)[:6000])
