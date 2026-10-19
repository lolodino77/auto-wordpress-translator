"""Extraction du titre, des tags et du texte d'un article à partir de son URL."""
import csv
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import trafilatura


def read_csv(path: str) -> list[tuple[str, list[str]]]:
    """Lit le CSV : une URL par ligne, étiquettes éventuelles en 2e colonne (séparées par ;). L'en-tête « url,tags » est
    facultatif : toute ligne dont la 1re cellule commence par http(s):// est une ligne de données."""
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            url = row[0].strip()
            if not re.match(r"https?://", url, re.I):
                continue  # en-tête (« url »), ligne vide ou commentaire
            tag_cell = ",".join(row[1:])  # étiquettes séparées par ; ou , (même si le CSV les a coupées en colonnes)
            tags = [t.strip() for t in tag_cell.replace(",", ";").split(";") if t.strip()]
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


# Section finale « Related articles » & co : un titre suivi seulement d'une liste de liens, jusqu'à la fin du texte
_RELATED_TAIL = re.compile(
    r"\n#{1,6}\s*(?:related|you (?:may|might) also like|more from|read next|recommended|further reading|articles? (?:liés?|connexes?))"
    r"[^\n]*\n(?:\s*(?:[-*]\s*)?\[[^\n]*\]\([^\n]*\)[^\n]*\n?)+\s*$",
    re.I,
)


def _clean_title(title: str, url: str) -> str:
    """Retire le suffixe « - Nom du site » du titre, seulement s'il correspond au domaine de l'URL."""
    domain = re.sub(r"[^a-z0-9]", "", urlparse(url).netloc.lower())
    parts = re.split(r"\s+[-|–—]\s+", title)
    if len(parts) > 1:
        suffix = re.sub(r"[^a-z0-9]", "", parts[-1].lower())
        if suffix and (suffix in domain or domain.removeprefix("www") in suffix):
            return " - ".join(parts[:-1]).strip()
    return title


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


# Appel de note de certains plugins WordPress : [<sup>1</sup>](#easy-footnote-bottom-1-123)
_NOTE_CALL = re.compile(r"\s*\[<sup>(\d{1,2})</sup>\]\([^)]*\)")
_NUMBERED = re.compile(r"^\s*\d{1,2}\.\s")


def _split_notes(paragraph: str) -> list[tuple[int, str]]:
    """Sépare « 1. texte2. texte » en notes numérotées ; si la numérotation n'est pas 1,2,3… on garde un bloc."""
    parts = re.split(r"(?:^|(?<=[.!?)\]”\"’]))\s*(\d{1,2})\.\s+(?=\S)", paragraph.strip())
    nums = [int(n) for n in parts[1::2]]
    if parts[0].strip() or not nums or nums != list(range(1, len(nums) + 1)):
        return [(1, _NUMBERED.sub("", paragraph.strip()))]
    return list(zip(nums, (t.strip() for t in parts[2::2])))


def _mark_calls(text: str, numbers: set[int]) -> str:
    """Remplace les appels de note par [NOTE n]. Les <sup>n</sup> sans lien ne sont des appels que si une note n existe."""
    text = _NOTE_CALL.sub(r" [NOTE \1]", text)
    return re.sub(r"(?<=\S)<sup>(\d{1,2})</sup>",
                  lambda m: f" [NOTE {m.group(1)}]" if int(m.group(1)) in numbers else m.group(0), text)


def _inline_notes(text: str) -> tuple[str, dict[int, str]]:
    """Format de certains sites : les notes sont des titres numérotés (« ###### 3. texte ») juste sous le paragraphe,
    avec des appels <sup>3</sup> sans lien. Reconnu seulement si la numérotation est 1..n ET que chaque n a son
    appel dans le texte (pour ne pas confondre avec des intertitres « 1. Introduction »)."""
    notes: dict[int, str] = {}
    for m in re.finditer(r"(?m)^#{1,6}\s*(\d{1,2})\.\s+(.+)$", text):
        notes.setdefault(int(m.group(1)), m.group(2).strip())
    nums = sorted(notes)
    if not nums or nums != list(range(1, len(nums) + 1)):
        return text, {}
    if not all(re.search(rf"<sup>{n}</sup>", text) for n in nums):
        return text, {}
    body = re.sub(r"(?m)^#{1,6}\s*\d{1,2}\.\s+.+$\n?", "", text)
    return re.sub(r"\n{3,}", "\n\n", body).rstrip(), notes


def _with_footnotes(precise: str, recall: str) -> str:
    body, inline = _inline_notes(precise)
    if inline:
        block = "\n\n".join(f"NOTE {n} : {t}" for n, t in inline.items())
        return _mark_calls(body, set(inline)) + "\n\n--- NOTES DE BAS DE PAGE DE LA SOURCE ---\n\n" + block
    return _with_recall_footnotes(precise, recall)


def _with_recall_footnotes(precise: str, recall: str) -> str:
    """Le mode « précision » écarte parfois les notes de bas de page (le mode « rappel » les garde) : on
    récupère les paragraphes de notes présents seulement dans le mode rappel et on les place à la fin sous
    la forme « NOTE n : texte », avec les appels « [NOTE n] » dans le texte. Sans cela le LLM invente les notes."""
    precise_pars = precise.split("\n\n")
    known = set(precise_pars)
    recall_notes = [p for p in recall.split("\n\n") if re.match(r"^\s*1\.\s", p) and p not in known]
    if not recall_notes:
        return _mark_calls(_RELATED_TAIL.sub("", precise).rstrip(), set())
    notes = [n for p in recall_notes for n in _split_notes(p)]
    note_texts = [t for _, t in notes]
    # retire du texte « précision » les restes de notes déjà couverts (numérotation faussée par la fusion)
    kept = [p for p in precise_pars if not (_NUMBERED.match(p) and _NUMBERED.sub("", p).strip() in " ".join(note_texts))]
    body = _RELATED_TAIL.sub("", "\n\n".join(kept).rstrip()).rstrip()  # après retrait des restes de notes
    block = "\n\n".join(f"NOTE {n} : {t}" for n, t in notes)
    return _mark_calls(body, {n for n, _ in notes}) + "\n\n--- NOTES DE BAS DE PAGE DE LA SOURCE ---\n\n" + block


def _text(html: str | None) -> str | None:
    if not html:
        return None
    kw = dict(output_format="markdown", include_formatting=True, include_links=True)
    # favor_precision évite les « articles liés » / appels aux dons en fin de page
    precise = trafilatura.extract(html, favor_precision=True, **kw)
    if not precise or len(precise) < 200:
        return None
    precise = _RELATED_TAIL.sub("", _JUNK_TAIL.sub("", precise).rstrip()).rstrip()
    return _with_footnotes(precise, trafilatura.extract(html, favor_recall=True, **kw) or "")


def extract(url: str) -> Article:
    html = trafilatura.fetch_url(url)
    text = _text(html)
    if not text:  # téléchargement simple insuffisant : on retente avec un navigateur
        html = _render(url)
        text = _text(html)
    if not text:
        raise RuntimeError(f"Texte introuvable (page bloquée, payante ou vide) : {url}")
    meta = trafilatura.extract_metadata(html)
    title = _clean_title((meta.title if meta and meta.title else url).strip(), url)
    tags = _split(getattr(meta, "tags", None)) + _split(getattr(meta, "categories", None))
    return Article(url=url, title=title, text=text, tags=tags)


# --- Articles fournis sous forme de fichiers markdown locaux (dossier input/articles_md/) ----------------------
_NOISE_LINE = re.compile(
    r"^(?:!\[[^\]]*\]\([^)]*\)"  # image seule
    r"|\*\*[^*]{0,40}\*\*"  # petit texte en gras seul : date, nombre de likes, « Share »
    r"|\[\*\*[^\]]{0,60}\*\*\]\([^)]*\)"  # lien en gras seul : auteur, nombre de commentaires
    r"|\[[^\]]{0,60}\]\([^)]*\)"  # lien seul court : « Subscribe », profil
    r"|\d{1,6})$",  # nombre seul
    re.I,
)


def find_source_url(text: str) -> str | None:
    """URL d'origine d'un article exporté de Substack : le lien « …/p/<slug>/comments » donne « …/p/<slug> »."""
    m = re.search(r"(https?://[^\s)\]]+/p/[^\s/)\]]+)/comments", text)
    return m.group(1) if m else None


def clean_markdown(text: str) -> str:
    """Retire le bruit d'un export (images, en-tête auteur/date/likes/« Share ») sans toucher au texte de l'article."""
    lines = text.replace("\r\n", "\n").split("\n")
    # 1. en-tête : on retire les lignes de bruit AVANT le premier vrai paragraphe (au moins 20 mots)
    first_para = next((i for i, l in enumerate(lines) if len(re.sub(r"[#*_\[\]()!]", " ", l).split()) >= 20
                       and not l.lstrip().startswith("#")), len(lines))
    head = [l for l in lines[:first_para] if l.strip() and not _NOISE_LINE.match(l.strip())]
    body = lines[first_para:]
    # 2. une longue phrase en titre (« ### Ed Feser argues… », chapeau de l'article) redevient un paragraphe
    head = [re.sub(r"^#{1,6}\s+", "", l) if len(l.split()) > 12 else l for l in head]
    # 3. images partout dans le corps
    body = [l for l in body if not re.fullmatch(r"\s*!\[[^\]]*\]\([^)]*\)\s*", l)]
    out = "\n\n".join(p for p in ("\n".join(head).strip(), "\n".join(body).strip()) if p)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _markdown_footnotes(text: str) -> str:
    """Notes markdown « [^1] » + définitions « [^1]: texte » -> appels « [NOTE n] » et bloc final (même format que les pages web)."""
    defs = re.findall(r"(?m)^\[\^([^\]]+)\]:\s*(.+(?:\n(?!\[\^|\n).+)*)", text)
    if not defs:
        return text
    number = {label: i for i, (label, _) in enumerate(defs, start=1)}
    body = re.sub(r"(?m)^\[\^[^\]]+\]:.*(?:\n(?!\[\^|\n).+)*\n?", "", text)
    body = re.sub(r"\[\^([^\]]+)\]", lambda m: f" [NOTE {number[m.group(1)]}]" if m.group(1) in number else m.group(0), body)
    block = "\n\n".join(f"NOTE {number[l]} : {' '.join(t.split())}" for l, t in defs)
    return re.sub(r"\n{3,}", "\n\n", body).rstrip() + "\n\n--- NOTES DE BAS DE PAGE DE LA SOURCE ---\n\n" + block


def article_from_markdown(path) -> Article:
    """Article à traduire à partir d'un fichier .md : titre = nom du fichier, texte nettoyé, URL d'origine si retrouvée."""
    from pathlib import Path

    p = Path(path)
    raw = p.read_text(encoding="utf-8-sig")
    text = _markdown_footnotes(clean_markdown(raw))
    if len(text) < 200:
        raise RuntimeError(f"Texte trop court dans {p.name} ({len(text)} caractères)")
    return Article(url=find_source_url(raw) or "", title=p.stem.strip(), text=text, tags=[])


if __name__ == "__main__":
    import sys

    a = extract(sys.argv[1])
    print("TITRE:", a.title)
    print("TAGS:", a.tags)
    print("MOTS:", len(a.text.split()))
    print(a.text[:800])
