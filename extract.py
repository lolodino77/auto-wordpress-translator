"""Extraction du titre, des tags et du texte d'un article à partir de son URL."""
import csv
import re
from dataclasses import dataclass, field

import trafilatura


def read_csv(path: str) -> list[tuple[str, list[str]]]:
    """Lit le CSV (colonnes url,tags ; tags séparés par ; ou ,) -> [(url, [tags])]."""
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            url = (row.get("url") or "").strip()
            if url:
                tags = [t.strip() for t in (row.get("tags") or "").replace(",", ";").split(";") if t.strip()]
                rows.append((url, tags))
    return rows


@dataclass
class Article:
    url: str
    title: str
    text: str  # markdown
    tags: list[str] = field(default_factory=list)


def _split(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = value.replace(";", ",").split(",")
    return [v.strip() for v in value if v and v.strip()]


# Lignes parasites récurrentes en fin d'article (à compléter au fil des sites rencontrés)
_JUNK_TAIL = re.compile(
    r"(\n\s*(To download Theopolis Lectures[^\n]*|CLOSE|Subscribe to[^\n]*|Sign up for[^\n]*newsletter[^\n]*))+\s*$",
    re.I,
)


def _render(url: str) -> str | None:
    """Secours : charge la page dans un vrai navigateur (sites en JavaScript ou qui bloquent les robots)."""
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(4000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def _text(html: str | None) -> str | None:
    if not html:
        return None
    text = trafilatura.extract(
        html,
        output_format="markdown",
        include_formatting=True,
        include_links=True,
        favor_precision=True,  # évite d'inclure les « articles liés » / appels aux dons en fin de page
    )
    if text:
        text = _JUNK_TAIL.sub("", text).rstrip()
    return text if text and len(text) >= 200 else None


def extract(url: str) -> Article:
    html = trafilatura.fetch_url(url)
    text = _text(html)
    if not text:  # téléchargement simple insuffisant : on retente avec un navigateur
        html = _render(url)
        text = _text(html)
    if not text:
        raise RuntimeError(f"Texte introuvable (page bloquée, payante ou vide) : {url}")
    meta = trafilatura.extract_metadata(html)
    title = (meta.title if meta and meta.title else url).strip()
    tags = _split(getattr(meta, "tags", None)) + _split(getattr(meta, "categories", None))
    return Article(url=url, title=title, text=text, tags=tags)


if __name__ == "__main__":
    import sys

    a = extract(sys.argv[1])
    print("TITRE:", a.title)
    print("TAGS:", a.tags)
    print("MOTS:", len(a.text.split()))
    print(a.text[:800])
