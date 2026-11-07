"""Capture the README screenshots from a running Iksir instance.

Usage:
    python3 scripts/capture_screenshots.py http://127.0.0.1:8111

Writes PNGs into screenshots/. The app must already be running; this script
does not start it. It drives a real browser, so what lands in the images is
what the app actually renders.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "screenshots"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8111"

# A fresh address each run, so re-running against a live server does not trip
# the "email already registered" path.
DEMO_EMAIL = f"demo+{int(time.time())}@iksir.dev"

DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}

GEFITINIB = "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC(=C(C=C3)F)Cl)OCCCN4CCOCC4"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # --- 1. Landing ---------------------------------------------------
        page = browser.new_page(viewport=DESKTOP)
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "01-landing.png"))
        print("wrote 01-landing.png")

        # --- 2. Register, then the workbench ------------------------------
        page.click("#authBtn")
        page.wait_for_selector("#authModal:not([hidden])", timeout=10000)
        page.click("#switchBtn")  # flip the modal into "create account" mode
        page.wait_for_timeout(300)
        page.fill("#authEmail", DEMO_EMAIL)
        page.fill("#authName", "Demo Researcher")
        page.fill("#authPassword", "demo-password-123")
        page.click("#authSubmit")
        page.wait_for_selector("#authModal", state="hidden", timeout=15000)
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "02-workbench.png"))
        print("wrote 02-workbench.png")

        # --- 3. Descriptors for a real molecule ---------------------------
        page.click('.tab[data-view="descriptors"]')
        page.wait_for_timeout(300)
        page.fill("#descInput", GEFITINIB)
        page.click("#descBtn")
        page.wait_for_selector("#descOut .desc-grid", timeout=15000)
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "03-descriptors.png"))
        print("wrote 03-descriptors.png")

        # --- 4. Screening results -----------------------------------------
        page.click('.tab[data-view="screen"]')
        page.wait_for_timeout(300)
        page.select_option("#targetSelect", "egfr")
        page.wait_for_timeout(300)
        # Tick every compound in the reference library.
        chips = page.query_selector_all("#libraryPick .chip")
        for chip in chips:
            chip.click()
        page.click("#screenBtn")
        page.wait_for_selector("#results .result", timeout=20000)
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "04-screening.png"))
        print(f"wrote 04-screening.png ({len(chips)} compounds)")

        # --- 5. Reference library -----------------------------------------
        page.click('.tab[data-view="library"]')
        page.wait_for_selector("#libraryGrid .lib-card", timeout=15000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "05-library.png"))
        print("wrote 05-library.png")

        # --- 6. Mobile ----------------------------------------------------
        mobile = browser.new_page(viewport=MOBILE, device_scale_factor=2)
        mobile.goto(BASE, wait_until="networkidle")
        mobile.wait_for_timeout(800)
        mobile.screenshot(path=str(OUT / "06-mobile.png"))
        print("wrote 06-mobile.png")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
