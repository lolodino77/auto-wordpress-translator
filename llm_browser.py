"""Pilote Gemini / ChatGPT dans un navigateur Playwright (profil persistant, connecté à la main).

ATTENTION : les sélecteurs CSS ci-dessous dépendent de l'interface des sites et changent
de temps en temps. S'ils cassent, ajuster uniquement le dictionnaire SITES.
"""
import re
import time
from pathlib import Path
from typing import NamedTuple

from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

SITES = {
    "gemini": {
        "url": "https://gemini.google.com/app",
        "input": "div.ql-editor[contenteditable='true'], rich-textarea div[contenteditable='true']",
        "code": "code-block code, pre code",
        "answer": "message-content",  # texte de la réponse (vérifié sur gemini.google.com, novembre 2026)
    },
    "gpt": {
        "url": "https://chatgpt.com/",
        "input": "#prompt-textarea, textarea#mobile-composer-prompt",
        "code": "pre code",
        "answer": "[data-message-author-role='assistant']",
    },
}

END_MARK = "<!--FIN-->"


class LLMUnavailable(Exception):
    """Site inutilisable (déconnecté, captcha, quota, interface changée…)."""


class LLMRefused(ValueError):
    """Le LLM a répondu sans traduire (« Je suis une IA basée sur du texte. Cela dépasse mes capacités. »…).
    Sous-classe de ValueError : la pipeline la traite comme une réponse refusée, donc nouvel essai dans une nouvelle
    conversation, puis moteur suivant."""


# Réponses typiques d'un refus ou d'un « bug » du LLM (il arrive que Gemini réponde ainsi à un long texte, sans raison).
_REFUSAL = re.compile(
    r"IA basée sur du texte|dépasse mes capacités|je ne (?:peux|suis) pas|text-based AI|"
    r"outside (?:of )?my capabilities|I can(?:no|')t help|I'm (?:not able|unable) to",
    re.I,
)
# Meilleur modèle de Gemini, choisi avant chaque envoi (menu « sélecteur de mode » à côté de la zone de saisie).
# Expressions cherchées dans le texte des choix du menu, par ordre de préférence. Un mode payant non accessible au compte
# (Gemini propose alors « Mettre à niveau ») est sauté puis évité pour le reste de la session. Réglable dans config.toml :
# [llm] gemini_modes / gemini_thinking. Vérifié sur gemini.google.com (compte gratuit, novembre 2026) : modes « Auto » et
# « Code et analyse » (4 Argon, payant), niveaux de réflexion « Bas », « Moyen », « Élevé ».
GEMINI_MODES = [r"\bPro\b", r"Argon|Code et analyse|Code (?:and|&) analysis", r"^Auto"]
GEMINI_THINKING = [r"Élevé|High", r"Moyen|Medium"]
GEMINI_PICKER = "[data-test-id='bard-mode-menu-button']"
GEMINI_MODE_ITEM = "[role=menuitemradio][data-test-id^='bard-mode-option-']"
THINKING_MENU = re.compile(r"Niveau de réflexion|Thinking level|Thinking", re.I)
UPSELL = re.compile(r"Mettre à niveau|Upgrade|Accédez à plus de modèles|Get more models", re.I)
NOT_NOW = re.compile(r"Pas maintenant|Not now|Non merci|No thanks", re.I)

POLL_S = 5  # secondes entre deux regards sur la page
STABLE_S = 90  # réponse inchangée depuis ce délai, sans traduction : terminée sans traduire


def installed_chrome() -> str | None:
    """Le Google Chrome installé sur l'ordinateur, s'il y en a un.

    Utilisé de préférence au Chromium fourni avec Playwright (« Chrome for Testing ») : Google refuse de s'y connecter
    à un compte, et ce Chromium ne charge même pas les pages quand il est ouvert sans être piloté. Les traductions et la
    fenêtre de connexion à Gemini utilisent donc le MÊME Chrome, sur le même profil : la connexion faite dans l'une sert
    à l'autre."""
    import os
    import shutil
    import sys

    if sys.platform.startswith("win"):
        bases = [os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        candidates = [Path(b) / "Google" / "Chrome" / "Application" / "chrome.exe" for b in bases if b]
    elif sys.platform == "darwin":
        candidates = [Path(p) / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome"
                      for p in ("/Applications", Path.home() / "Applications")]
    else:
        candidates = [Path(p) for p in (shutil.which("google-chrome"), shutil.which("google-chrome-stable")) if p]
    return next((str(c) for c in candidates if c.is_file()), None)


def pick(texts: list[str], prefs: list[str], skip=frozenset()) -> int | None:
    """Indice du choix préféré parmi les textes d'un menu (préférences = expressions, la première l'emporte)."""
    for pref in prefs:
        for i, text in enumerate(texts):
            if text not in skip and re.search(pref, text, re.I):
                return i
    return None


class Browser:
    def __init__(self, profile_dir: str, headless: bool = False, prefs: dict | None = None, log=None):
        self.profile_dir = str(Path(profile_dir).resolve())
        self.headless = headless
        self._pw = None
        self.ctx = None
        prefs = prefs or {}
        self.gemini_modes = list(prefs.get("gemini_modes") or GEMINI_MODES)
        self.gemini_thinking = list(prefs.get("gemini_thinking") or GEMINI_THINKING)
        self._log = log or (lambda msg: None)
        self._locked: set[str] = set()  # modes payants refusés pendant cette session : plus essayés
        self._chosen = None  # libellé du sélecteur une fois le meilleur modèle choisi (évite de rouvrir le menu)

    def __enter__(self):
        self._pw = sync_playwright().start()
        chrome = installed_chrome()  # sinon : le Chromium fourni avec Playwright
        self.ctx = self._pw.chromium.launch_persistent_context(
            self.profile_dir, headless=self.headless, viewport={"width": 1280, "height": 900},
            **({"executable_path": chrome} if chrome else {}),
            # moins visiblement « piloté » : Google se méfie des navigateurs automatisés
            ignore_default_args=["--enable-automation"], args=["--disable-blink-features=AutomationControlled"],
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
                page.wait_for_selector(site["input"], timeout=60_000)
            except PWTimeout:
                raise LLMUnavailable(f"{engine}: zone de saisie introuvable (déconnecté ou captcha ?)")
            if engine == "gemini":
                self._best_gemini_model(page)
            # La page se re-rend parfois pendant le chargement : on re-localise la zone de saisie à chaque essai
            # (un élément déjà trouvé peut être détaché du DOM) et on retente une fois.
            for attempt in (1, 2):
                try:
                    _dismiss_banners(page)
                    page.locator(site["input"]).first.click(timeout=30_000)
                    # Insertion du texte d'un bloc (instantané, contrairement à une frappe touche par touche)
                    page.keyboard.insert_text(prompt)
                    page.wait_for_timeout(1500)
                    page.keyboard.press("Enter")
                    break
                except PWError as e:
                    if attempt == 2:
                        raise LLMUnavailable(f"{engine}: saisie impossible ({str(e).splitlines()[0]})")
                    page.wait_for_timeout(3000)
            return self._wait_answer(page, site["code"], engine, timeout_s, site.get("answer"))
        except PWError as e:  # toute autre erreur Playwright : on laisse l'agent passer au moteur suivant
            raise LLMUnavailable(f"{engine}: erreur navigateur ({str(e).splitlines()[0]})")
        finally:
            page.close()

    def _best_gemini_model(self, page) -> None:
        """Choisit le meilleur mode accessible et le niveau de réflexion le plus élevé. Ne bloque jamais la traduction :
        si le menu a changé ou ne répond pas, on garde le modèle actuel (et on le dit dans le journal)."""
        picker = page.locator(GEMINI_PICKER).first
        try:
            picker.wait_for(state="visible", timeout=10_000)
            before = picker.get_attribute("aria-label") or ""
            if self._chosen and before == self._chosen:
                return  # déjà réglé dans cette session (Gemini s'en souvient d'une conversation à l'autre)
            _dismiss_banners(page)
            self._choose(page, picker, GEMINI_MODE_ITEM, self.gemini_modes, submenu=None)
            self._choose(page, picker, f"[role=menuitemradio]:not({GEMINI_MODE_ITEM})", self.gemini_thinking,
                         submenu=THINKING_MENU)
            after = picker.get_attribute("aria-label") or ""
            label = re.sub(r"^.*(?:actuellement|currently)\s*", "", after, flags=re.I).strip() or after
            if after != self._chosen:
                self._log(f"Gemini : modèle choisi « {label} » (le meilleur accessible à ce compte).")
            self._chosen = after
        except (PWError, PWTimeout) as e:
            self._log(f"Gemini : choix du modèle impossible ({str(e).splitlines()[0][:120]}) ; modèle actuel conservé.")
        finally:
            try:
                _close_menus(page)
            except PWError:
                pass

    def _choose(self, page, picker, item_sel: str, prefs: list[str], submenu) -> None:
        """Ouvre le menu (et le sous-menu), puis clique le choix préféré ; saute les choix payants refusés."""
        for _ in range(4):  # au plus quelques modes payants à sauter
            _close_menus(page)
            picker.click(timeout=5_000)
            page.locator("[role=menuitemradio]:visible").first.wait_for(timeout=5_000)
            if submenu is not None:
                page.get_by_role("menuitem", name=submenu).first.click(timeout=5_000)
                page.wait_for_timeout(600)
            items = page.locator(f"{item_sel}:visible")
            texts = [" ".join(t.split()) for t in items.all_inner_texts()]
            i = pick(texts, prefs, self._locked)
            if i is None:
                return  # aucun choix connu : on garde l'actuel
            if items.nth(i).get_attribute("aria-checked") == "true":
                return  # déjà sélectionné
            items.nth(i).click(timeout=5_000)
            page.wait_for_timeout(1500)
            if not _refuse_upsell(page):
                return  # choisi
            self._locked.add(texts[i])
            self._log(f"Gemini : « {texts[i]} » est réservé aux abonnements payants ; choix suivant.")

    @staticmethod
    def _wait_answer(page, code_sel: str, engine: str, timeout_s: int, answer_sel: str | None = None) -> str:
        """Attend le bloc de code terminé par <!--FIN-->. Si le LLM a fini de répondre SANS ce bloc (refus, réponse
        à côté), lève LLMRefused tout de suite au lieu d'attendre la fin du délai (10 minutes)."""
        deadline = time.time() + timeout_s
        last_text, same_polls = None, 0
        while time.time() < deadline:
            page.wait_for_timeout(POLL_S * 1000)
            if re.search(r"Impossible de se connecter|Something went wrong|Une erreur est survenue",
                         page.inner_text("body")):
                raise LLMUnavailable(f"{engine}: le site a refusé la requête (connexion requise ?)")
            blocks = page.locator(code_sel)
            if blocks.count():
                text = blocks.last.inner_text()
                if END_MARK in text:
                    return text
                last_text, same_polls = None, 0  # traduction en cours d'écriture : on attend
                continue
            if not answer_sel:
                continue
            answers = page.locator(answer_sel)
            answer = answers.last.inner_text().strip() if answers.count() else ""
            if not answer:
                continue
            same_polls = same_polls + 1 if answer == last_text else 0
            last_text = answer
            excerpt = " ".join(answer.split())[:160]
            if same_polls >= 1 and _REFUSAL.search(answer):
                raise LLMRefused(f"{engine} a répondu sans traduire : « {excerpt} »")
            if same_polls * POLL_S >= STABLE_S:
                raise LLMRefused(f"{engine} a terminé sa réponse sans la traduction attendue : « {excerpt} »")
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
        btn = page.get_by_role(role, name=_DISMISS)
        if not btn.count():  # rien à fermer : on n'attend pas (avant : 2 × 3 s perdues à chaque article)
            continue
        try:
            btn.first.click(timeout=3000)
            page.wait_for_timeout(800)
        except (PWTimeout, PWError):
            pass


def _close_menus(page) -> None:
    for _ in range(3):  # menu, puis sous-menu
        if not page.locator("[role=menuitemradio]:visible, [role=menuitem]:visible").count():
            return
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def _refuse_upsell(page) -> bool:
    """Ferme l'offre « Mettre à niveau » si elle s'est ouverte (jamais d'achat : on clique « Pas maintenant »).
    Renvoie True si une offre était affichée, donc si le choix n'est pas accessible à ce compte."""
    dialog = page.locator("mat-dialog-container, [role=dialog], [role=alertdialog]").filter(has_text=UPSELL)
    if not dialog.count():
        return False
    try:
        dialog.first.get_by_role("button", name=NOT_NOW).first.click(timeout=3_000)
    except (PWError, PWTimeout):
        page.keyboard.press("Escape")
    page.wait_for_timeout(800)
    return True


def _first_match(page, selector: str) -> str:
    for sel in (s.strip() for s in selector.split(",")):
        if page.locator(sel).count():
            return sel
    return selector


class Answer(NamedTuple):
    title: str
    tags: list[str]
    category: str | None  # None si le LLM n'en a pas proposé
    html: str
    to_check: list[str]  # points signalés par le LLM pour la relecture humaine
    slug: str | None = None  # identifiant (URL) proposé par le LLM, à nettoyer avec rules.make_slug
    summary: str | None = None  # résumé de la thèse de l'auteur, pour l'introduction du traducteur


def parse_answer(raw: str) -> Answer:
    """Découpe la réponse du LLM : TITRE, puis TAGS / CATEGORIE / SLUG (dans cet ordre ou non), '---', corps HTML,
    <!--A_VERIFIER:...-->."""
    raw = raw.replace(END_MARK, "").strip()
    m = re.search(r"TITRE\s*:\s*(.+?)\s*\n(.*?)\n\s*-{3,}\s*\n(.*)", raw, re.S)
    if not m:
        raise ValueError("Format de réponse inattendu (TITRE/TAGS/--- manquants)")
    fields = {k.upper(): v.strip() for k, v in re.findall(r"(?m)^\s*(TAGS|CATEGORIE|SLUG|RESUME)\s*:\s*(.*)$", m.group(2))}
    if not fields.get("TAGS"):
        raise ValueError("Format de réponse inattendu (TAGS manquant)")
    title, tags, category, slug, html = m.group(1), fields["TAGS"], fields.get("CATEGORIE"), fields.get("SLUG"), m.group(3).strip()
    to_check: list[str] = []
    check = re.search(r"<!--\s*A_VERIFIER\s*:(.*?)-->", html, re.S)
    if check:
        items = (re.sub(r"\s*;\s*rien\s*$", "", s.strip(), flags=re.I) for s in re.split(r"\s*;;\s*|\n", check.group(1)))
        to_check = [s for s in items if s and s.lower() != "rien"]
        html = (html[: check.start()] + html[check.end():]).strip()
    if category and category.strip().lower() in {"aucune", "aucun", "none", ""}:
        category = None
    # Garde-fou : le LLM a parfois recopié l'anglais sans traduire
    en = len(re.findall(r"\b(the|and|of|that|is)\b", html, re.I))
    fr = len(re.findall(r"\b(le|la|les|des|et|est|que|une?)\b", html, re.I))
    if en > fr:
        raise ValueError("La réponse semble ne pas être traduite en français")
    # séparateur = virgule, sauf entre deux chiffres (« Jérémie 29,11 » est UNE étiquette)
    return Answer(title, [t.strip() for t in re.split(r"(?<!\d),|,(?!\d)", tags) if t.strip()], category and category.strip(), html, to_check,
                  slug or None, fields.get("RESUME") or None)
