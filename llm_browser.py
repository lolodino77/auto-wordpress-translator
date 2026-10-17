"""Pilote Gemini / ChatGPT dans un navigateur Playwright (profil persistant, connecté à la main).

ATTENTION : les sélecteurs CSS ci-dessous dépendent de l'interface des sites et changent
de temps en temps. S'ils cassent, ajuster uniquement le dictionnaire SITES.
"""
import re
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

SITES = {
    "gemini": {
        "url": "https://gemini.google.com/app",
        "input": "div.ql-editor[contenteditable='true'], rich-textarea div[contenteditable='true']",
        "code": "code-block code, pre code",
    },
    "gpt": {
        "url": "https://chatgpt.com/",
        "input": "#prompt-textarea, textarea#mobile-composer-prompt",
        "code": "pre code",
    },
}

END_MARK = "<!--FIN-->"


class LLMUnavailable(Exception):
    """Site inutilisable (déconnecté, captcha, quota, interface changée…)."""


class Browser:
    def __init__(self, profile_dir: str, headless: bool = False):
        self.profile_dir = str(Path(profile_dir).resolve())
        self.headless = headless
        self._pw = None
        self.ctx = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        self.ctx = self._pw.chromium.launch_persistent_context(
            self.profile_dir, headless=self.headless, viewport={"width": 1280, "height": 900}
        )
        return self

    def __exit__(self, *exc):
        self.ctx.close()
        self._pw.stop()

    def login_session(self):
        """Ouvre les deux sites pour que l'utilisateur s'y connecte à la main."""
        for name, site in SITES.items():
            page = self.ctx.new_page()
            page.goto(site["url"])
            print(f"Connectez-vous à {name} dans la fenêtre, puis revenez ici.")
        input("Appuyez sur Entrée quand c'est fait… ")

    def translate(self, engine: str, prompt: str, timeout_s: int = 600) -> str:
        site = SITES[engine]
        page = self.ctx.new_page()
        try:
            page.goto(site["url"], wait_until="domcontentloaded")
            try:
                box = page.wait_for_selector(site["input"], timeout=60_000)
            except PWTimeout:
                raise LLMUnavailable(f"{engine}: zone de saisie introuvable (déconnecté ou captcha ?)")
            _dismiss_banners(page)
            box.click()
            # Insertion du texte d'un bloc (instantané, contrairement à une frappe touche par touche)
            page.keyboard.insert_text(prompt)
            page.wait_for_timeout(1500)
            page.keyboard.press("Enter")
            return self._wait_answer(page, site["code"], engine, timeout_s)
        finally:
            page.close()

    @staticmethod
    def _wait_answer(page, code_sel: str, engine: str, timeout_s: int) -> str:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            page.wait_for_timeout(5000)
            if re.search(r"Impossible de se connecter|Something went wrong|Une erreur est survenue",
                         page.inner_text("body")):
                raise LLMUnavailable(f"{engine}: le site a refusé la requête (connexion requise ?)")
            blocks = page.locator(code_sel)
            if blocks.count():
                text = blocks.last.inner_text()
                if END_MARK in text:
                    return text
        raise LLMUnavailable(f"{engine}: pas de réponse complète après {timeout_s}s")


# Bannières de cookies / invitations à se connecter : on ne clique que sur les options
# qui REFUSENT (jamais « Tout accepter »).
_DISMISS = re.compile(
    r"Tout refuser|Refuser tout|Reject all|Refuser les cookies non essentiels|"
    r"Reject non-essential|Rester déconnecté|Stay logged out",
    re.I,
)


def _dismiss_banners(page) -> None:
    for role in ("button", "link"):
        btn = page.get_by_role(role, name=_DISMISS).first
        try:
            btn.click(timeout=3000)
            page.wait_for_timeout(800)
        except PWTimeout:
            pass


def _first_match(page, selector: str) -> str:
    for sel in (s.strip() for s in selector.split(",")):
        if page.locator(sel).count():
            return sel
    return selector


def parse_answer(raw: str) -> tuple[str, list[str], str]:
    """Découpe la réponse du LLM en (titre, tags, html)."""
    raw = raw.replace(END_MARK, "").strip()
    m = re.search(r"TITRE\s*:\s*(.+?)\s*\n\s*TAGS\s*:\s*(.+?)\s*\n-{3,}\s*\n(.*)", raw, re.S)
    if not m:
        raise ValueError("Format de réponse inattendu (TITRE/TAGS/--- manquants)")
    title, tags, html = m.group(1), m.group(2), m.group(3).strip()
    # Garde-fou : le LLM a parfois recopié l'anglais sans traduire
    en = len(re.findall(r"\b(the|and|of|that|is)\b", html, re.I))
    fr = len(re.findall(r"\b(le|la|les|des|et|est|que|une?)\b", html, re.I))
    if en > fr:
        raise ValueError("La réponse semble ne pas être traduite en français")
    return title, [t.strip() for t in tags.split(",") if t.strip()], html
