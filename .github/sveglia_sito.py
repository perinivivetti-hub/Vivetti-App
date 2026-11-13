"""Sveglia il sito Streamlit di Vivetti App.

Apre l'indirizzo come farebbe un browser vero (una semplice richiesta non basta, perché
Streamlit risponde "200 OK" ma lascia l'app addormentata). Se compare la schermata
"This app has gone to sleep", clicca il pulsante per risvegliarla e aspetta che l'app sia
caricata. Esce con errore se non ci riesce, così GitHub avvisa con una email.
"""
import os
import re
import sys
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

URL = os.environ["APP_URL"].strip()
ATTESA_MAX_SECONDI = 240


def app_caricata(page) -> bool:
    """True se in una qualsiasi cornice della pagina c'è l'app Streamlit con del testo."""
    for frame in page.frames:
        try:
            app = frame.locator('[data-testid="stApp"]')
            if app.count() > 0 and len(app.first.inner_text(timeout=2000).strip()) > 0:
                return True
        except Exception:
            continue
    return False


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        print(f"Apro {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        # 1) Se l'app dorme, compare il pulsante di risveglio
        pulsante = page.get_by_role("button", name=re.compile(r"get this app back up", re.I))
        try:
            pulsante.wait_for(state="visible", timeout=20_000)
            print("L'app era addormentata: clicco il pulsante di risveglio")
            pulsante.click()
        except PlaywrightTimeout:
            print("Nessun pulsante di risveglio: l'app è già sveglia o si sta caricando")

        # 2) Aspetto che l'app sia davvero caricata
        inizio = time.time()
        while time.time() - inizio < ATTESA_MAX_SECONDI:
            if app_caricata(page):
                print(f"App caricata dopo {int(time.time() - inizio)} secondi")
                browser.close()
                return 0
            time.sleep(5)

        page.screenshot(path="sveglia_errore.png", full_page=True)
        print("ERRORE: l'app non risulta caricata entro il tempo massimo")
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
