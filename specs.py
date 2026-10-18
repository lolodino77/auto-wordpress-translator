"""Lecture des spécifications éditoriales : tous les PDF du dossier spec/ sont lus à chaque exécution
et injectés dans le prompt. Modifier ou ajouter un PDF suffit à changer les règles données au LLM."""
import re
from pathlib import Path

from pypdf import PdfReader


def _clean(raw: str) -> str:
    """Le texte extrait des PDF met souvent un mot par ligne : on le remet en phrases."""
    text = re.sub(r"[ \t\r\f\v]*\n[ \t\r\f\v]*", " ", raw)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\s*●\s*", "\n● ", text)  # puces des règles de rédaction
    text = re.sub(r"\s+(o\s+à\s)", r"\n   - à ", text)  # sous-puces
    text = re.sub(r"\s+((?:[A-C])\. ?\d+(?:\. ?\d+)* ?:)", r"\n\1", text)  # A.2.3 : du guide des références
    return text.strip()


def load_specs(spec_dir: str = "spec", exclude_after: dict[str, str] | None = None) -> str:
    """Retourne le texte de toutes les specs. Échoue s'il n'y en a aucune (jamais de traduction sans règles).

    exclude_after : {nom du PDF: marqueur} -> tout ce qui suit le marqueur est ignoré (passages hors sujet,
    par exemple le tutoriel Zotero à la fin du guide des références).
    """
    pdfs = sorted(Path(spec_dir).glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"Aucun PDF de spécification dans {spec_dir}/")
    parts = []
    for pdf in pdfs:
        text = _clean("\n".join(page.extract_text() or "" for page in PdfReader(pdf).pages))
        if len(text) < 200:
            raise ValueError(f"{pdf.name} : texte illisible (PDF scanné ?)")
        marker = (exclude_after or {}).get(pdf.name)
        if marker:
            if marker not in text:
                raise ValueError(f"{pdf.name} : marqueur de coupe introuvable ({marker!r}), vérifier config.toml")
            text = text.split(marker, 1)[0].strip()
        parts.append(f"### {pdf.stem}\n{text}")
    return "\n\n".join(parts)
